import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:flutter/services.dart' show MissingPluginException;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';

enum OcrRunPhase {
  idle,

  /// Walking the chapter's pages through the platform engine.
  recognizing,

  /// Every page recognized; `POST /ocr/chapter` in flight.
  uploading,

  /// Held because the app is backgrounded — resumes on foreground.
  paused,

  done,
  failed,
  cancelled,
}

class OcrRunState {
  const OcrRunState({
    this.phase = OcrRunPhase.idle,
    this.chapter,
    this.completedPages = 0,
    this.totalPages = 0,
    this.wordCount = 0,
    this.message,
  });

  final OcrRunPhase phase;
  final ChapterIdentity? chapter;
  final int completedPages;
  final int totalPages;

  /// Words the server says it stored — the only proof the upload was taken
  /// rather than quietly discarded as an empty transcript.
  final int wordCount;

  /// Failure reason when [phase] is [OcrRunPhase.failed]; otherwise unset.
  final String? message;

  bool get isBusy =>
      phase == OcrRunPhase.recognizing ||
      phase == OcrRunPhase.uploading ||
      phase == OcrRunPhase.paused;

  /// 0..1 while recognizing, `null` before the page count is known — the
  /// distinction a determinate vs indeterminate progress indicator needs.
  double? get progress =>
      totalPages <= 0 ? null : completedPages / totalPages;

  OcrRunState copyWith({
    OcrRunPhase? phase,
    ChapterIdentity? chapter,
    int? completedPages,
    int? totalPages,
    int? wordCount,
    String? message,
  }) =>
      OcrRunState(
        phase: phase ?? this.phase,
        chapter: chapter ?? this.chapter,
        completedPages: completedPages ?? this.completedPages,
        totalPages: totalPages ?? this.totalPages,
        wordCount: wordCount ?? this.wordCount,
        message: message ?? this.message,
      );
}

/// Runs OCR over one downloaded chapter and uploads the transcript (spec §4).
///
/// **Only downloaded chapters.** The page list comes from
/// `DownloadsStore.localPagePaths`, which returns real, existence-checked
/// files — nothing here ever fetches a page over the network, because OCR is
/// a use for bytes already on the phone, not a reason to spend more.
///
/// **One page per channel call, not one call per chapter**, even though
/// `OcrEngine.recognize` takes a list. A 60-page chapter is a minute or more
/// of native work; batching it into a single invocation would make progress
/// unreportable and cancellation impossible, which spec §4 calls out
/// explicitly. Per-call overhead is microseconds against ~a second of Vision
/// work, so the loop costs nothing real.
///
/// **One run at a time.** A second `runChapter` while one is in flight is
/// refused rather than queued: OCR is user-initiated per chapter, and two
/// concurrent runs would compete for the same native recognizer for no
/// benefit. (Contrast the download queue, which is genuinely a queue because
/// "download this whole series" is a single gesture.)
class OcrRunController extends Notifier<OcrRunState> {
  var _cancelled = false;
  var _foreground = true;
  Completer<void>? _foregroundGate;
  Future<void>? _activeRun;

  /// Awaits the current run, if any — **test-only**, mirroring
  /// `DownloadQueueController.debugWaitUntilIdle`. Production callers fire
  /// [runChapter] and watch the state.
  @visibleForTesting
  Future<void> debugWaitUntilIdle() => _activeRun ?? Future<void>.value();

  @override
  OcrRunState build() => const OcrRunState();

  /// Recognizes every downloaded page of [id] and uploads the result.
  /// Fire-and-forget from the UI; progress arrives through [state].
  Future<void> runChapter({
    required ChapterIdentity id,
    double? chapterNumber,
  }) {
    if (state.isBusy) return _activeRun ?? Future<void>.value();
    _cancelled = false;
    final run = _run(id: id, chapterNumber: chapterNumber);
    _activeRun = run;
    return run;
  }

  /// Stops the run before its next page. Already-recognized pages are
  /// discarded rather than uploaded: a half-transcript would *replace* a
  /// complete one server-side (the ingest upsert is last-write-wins), so
  /// uploading what we have would actively destroy data on a chapter someone
  /// else already OCR'd properly.
  void cancel() {
    if (!state.isBusy) return;
    _cancelled = true;
    _openForegroundGate();
  }

  /// Foreground gating, same contract as the download queue: a backgrounded
  /// app holds between pages instead of racing a suspend, and picks up where
  /// it left off on resume. Nothing is lost — the recognized pages so far
  /// live in this run's own local list.
  void setForeground(bool foreground) {
    if (_foreground == foreground) return;
    _foreground = foreground;
    if (foreground) {
      _openForegroundGate();
    } else if (state.phase == OcrRunPhase.recognizing) {
      state = state.copyWith(phase: OcrRunPhase.paused);
    }
  }

  void _openForegroundGate() {
    final gate = _foregroundGate;
    _foregroundGate = null;
    if (gate != null && !gate.isCompleted) gate.complete();
  }

  Future<void> _awaitForeground() {
    if (_foreground || _cancelled) return Future<void>.value();
    final gate = _foregroundGate ??= Completer<void>();
    return gate.future;
  }

  Future<void> _run({
    required ChapterIdentity id,
    double? chapterNumber,
  }) async {
    state = OcrRunState(phase: OcrRunPhase.recognizing, chapter: id);

    final store = ref.read(downloadsStoreProvider);
    if (store == null) {
      return _fail(id, 'Choose a reading profile first.');
    }

    final Map<int, File> pageFiles;
    try {
      pageFiles = await store.localPagePaths(id);
    } catch (_) {
      return _fail(id, 'Could not read this chapter from storage.');
    }
    if (pageFiles.isEmpty) {
      return _fail(id, 'Download this chapter before running OCR on it.');
    }

    final pageNumbers = pageFiles.keys.toList()..sort();
    state = state.copyWith(totalPages: pageNumbers.length);

    final engine = ref.read(ocrEngineProvider);
    final recognized = <PageText>[];

    for (final pageNumber in pageNumbers) {
      await _awaitForeground();
      if (_cancelled) return _cancelledOut(id);
      if (state.phase == OcrRunPhase.paused) {
        state = state.copyWith(phase: OcrRunPhase.recognizing);
      }

      try {
        final results = await engine.recognize(
          [pageFiles[pageNumber]!.path],
          startPage: pageNumber,
        );
        if (results.isNotEmpty) recognized.add(results.first);
      } on MissingPluginException {
        // The engine itself is gone, not one bad page — every remaining page
        // would fail identically, so stop rather than burn a minute proving
        // it. (Capability detection normally hides the button long before
        // this; this is the race where it doesn't.)
        return _fail(id, 'OCR is not available on this device.');
      } catch (_) {
        // One unreadable page (a truncated blob, an image format the
        // platform decoder rejects) must not cost the other 59.
      }

      state = state.copyWith(completedPages: state.completedPages + 1);
    }

    if (_cancelled) return _cancelledOut(id);
    if (recognized.every((page) => page.isEmpty)) {
      return _fail(id, 'No text was found in this chapter.');
    }

    state = state.copyWith(phase: OcrRunPhase.uploading);
    final result = await ref.read(ocrRepositoryProvider).uploadChapter(
          id: id,
          pages: recognized,
          engine: await engine.engineId(),
          chapterNumber: chapterNumber,
        );

    if (result.isErr) return _fail(id, result.error.userMessage);

    state = state.copyWith(phase: OcrRunPhase.done, wordCount: result.value);
    // The "already OCR'd" affordance reads coverage, so it has to be re-asked
    // now rather than at some later cache expiry.
    ref.invalidate(
      ocrCoverageProvider((sourceId: id.sourceId, seriesKey: id.seriesKey)),
    );
  }

  void _fail(ChapterIdentity id, String message) {
    state = state.copyWith(
      phase: OcrRunPhase.failed,
      chapter: id,
      message: message,
    );
  }

  void _cancelledOut(ChapterIdentity id) {
    state = state.copyWith(phase: OcrRunPhase.cancelled, chapter: id);
  }
}

final ocrRunControllerProvider =
    NotifierProvider<OcrRunController, OcrRunState>(
  OcrRunController.new,
  name: 'ocrRunController',
);
