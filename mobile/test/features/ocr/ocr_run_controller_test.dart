import 'dart:async';

import 'package:flutter/services.dart' show MissingPluginException;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/ocr/controllers/ocr_run_controller.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_coverage.dart';
import 'package:manhwamaniacs/features/ocr/models/ocr_search_result.dart';
import 'package:manhwamaniacs/features/ocr/models/page_text.dart';
import 'package:manhwamaniacs/features/ocr/providers/ocr_providers.dart';
import 'package:manhwamaniacs/features/ocr/repositories/ocr_repository.dart';
import 'package:manhwamaniacs/features/ocr/services/ocr_engine.dart';

import '../../support/downloads_test_support.dart';

const _id = (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: 'c1');

/// Waits for [condition], failing the test rather than hanging forever if it
/// never becomes true.
Future<void> _waitUntil(
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 5),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      fail('condition was never met within $timeout');
    }
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}

/// An [OcrEngine] whose per-path behaviour is fully scripted, so a test can
/// simulate one unreadable page, a vanished platform handler, or a run slow
/// enough to be cancelled halfway through.
class _ScriptedOcrEngine implements OcrEngine {
  _ScriptedOcrEngine(this._recognize, {this.onRecognize});

  final Future<String> Function(String path) _recognize;
  final void Function(String path)? onRecognize;
  final recognizedPaths = <String>[];

  @override
  Future<bool> isAvailable() async => true;

  @override
  Future<String> engineId() async => 'test-engine';

  @override
  Future<List<PageText>> recognize(
    List<String> imagePaths, {
    int startPage = 1,
  }) async {
    final results = <PageText>[];
    for (var i = 0; i < imagePaths.length; i++) {
      recognizedPaths.add(imagePaths[i]);
      onRecognize?.call(imagePaths[i]);
      results.add(
        PageText(page: startPage + i, text: await _recognize(imagePaths[i])),
      );
    }
    return results;
  }
}

class _RecordingOcrRepository implements OcrRepository {
  _RecordingOcrRepository({this.result = const Ok(42)});

  final Result<int> result;
  final uploads = <({ChapterIdentity id, List<PageText> pages, String engine})>[];

  @override
  Future<Result<int>> uploadChapter({
    required ChapterIdentity id,
    required List<PageText> pages,
    required String engine,
    double? chapterNumber,
    String? language,
  }) async {
    uploads.add((id: id, pages: pages, engine: engine));
    return result;
  }

  @override
  Future<Result<OcrCoverage>> coverage({
    required String sourceId,
    required String seriesKey,
  }) async =>
      const Ok(OcrCoverage.empty);

  @override
  Future<Result<OcrSearchPage>> search(
    String query, {
    int limit = 20,
    int offset = 0,
  }) async =>
      const Ok(OcrSearchPage.empty);
}

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  /// Puts a fully-downloaded chapter on disk — the only kind OCR ever reads.
  /// [pageNumbers] are the store's real page numbers, so a test can create a
  /// chapter with a gap (a blob deleted by hand through the Files app).
  Future<DownloadsStore> seedDownloadedChapter({
    List<int> pageNumbers = const [1, 2, 3],
  }) async {
    final store = harness.storeFor('u1p1');
    final rowId = await store.ensureQueued(id: _id, chapterNumber: 1);
    await store.updateManifestInfo(rowId: rowId, pageCount: pageNumbers.length);
    for (final number in pageNumbers) {
      await store.savePage(
        rowId: rowId,
        pageNumber: number,
        bytes: [number, number, number],
      );
    }
    await store.markCompleteIfAllPagesPresent(rowId);
    return store;
  }

  ProviderContainer buildContainer({
    required OcrEngine engine,
    required OcrRepository repository,
    bool withStore = true,
  }) {
    final container = ProviderContainer(
      overrides: [
        downloadsStoreProvider.overrideWithValue(
          withStore ? harness.storeFor('u1p1') : null,
        ),
        ocrEngineProvider.overrideWithValue(engine),
        ocrRepositoryProvider.overrideWithValue(repository),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  group('happy path', () {
    test('recognizes every downloaded page and uploads the transcript',
        () async {
      await seedDownloadedChapter();
      final engine = _ScriptedOcrEngine((path) async => 'text for $path');
      final repository = _RecordingOcrRepository();
      final container = buildContainer(engine: engine, repository: repository);

      final controller = container.read(ocrRunControllerProvider.notifier);
      await controller.runChapter(id: _id, chapterNumber: 1);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.done);
      expect(state.completedPages, 3);
      expect(state.totalPages, 3);
      expect(state.wordCount, 42);

      expect(repository.uploads, hasLength(1));
      expect(repository.uploads.single.id, _id);
      expect(repository.uploads.single.engine, 'test-engine');
      expect(repository.uploads.single.pages, hasLength(3));
    });

    test('stamps the store\'s real page numbers, gaps and all', () async {
      // Pages 1, 2 and 5 — page 3/4's blobs were deleted by hand. The
      // transcript must say 5, not 3, or the text lands on the wrong page.
      await seedDownloadedChapter(pageNumbers: [1, 2, 5]);
      final repository = _RecordingOcrRepository();
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => 'words'),
        repository: repository,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      expect(
        repository.uploads.single.pages.map((p) => p.page),
        [1, 2, 5],
      );
    });
  });

  group('refusals', () {
    test('fails without uploading when there is no active profile', () async {
      final repository = _RecordingOcrRepository();
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => 'words'),
        repository: repository,
        withStore: false,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      expect(container.read(ocrRunControllerProvider).phase, OcrRunPhase.failed);
      expect(repository.uploads, isEmpty);
    });

    test('fails without uploading when the chapter is not downloaded',
        () async {
      final repository = _RecordingOcrRepository();
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => 'words'),
        repository: repository,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.failed);
      expect(state.message, contains('Download this chapter'));
      expect(repository.uploads, isEmpty);
    });

    test('never uploads an all-empty transcript over a stored one', () async {
      // The ingest service keeps an existing transcript when the incoming
      // word count is 0, but spending a POST to be ignored — and reporting
      // success for it — would be a lie about what happened.
      await seedDownloadedChapter();
      final repository = _RecordingOcrRepository();
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => '   '),
        repository: repository,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.failed);
      expect(state.message, contains('No text'));
      expect(repository.uploads, isEmpty);
    });

    test('surfaces an upload failure instead of claiming success', () async {
      await seedDownloadedChapter();
      final repository = _RecordingOcrRepository(
        result: const Err(ValidationError('Server said no.')),
      );
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => 'words'),
        repository: repository,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.failed);
      expect(state.message, 'Server said no.');
    });
  });

  group('per-page failure isolation', () {
    test('one unreadable page does not cost the rest of the chapter',
        () async {
      await seedDownloadedChapter();
      var call = 0;
      final repository = _RecordingOcrRepository();
      final container = buildContainer(
        engine: _ScriptedOcrEngine((path) async {
          call++;
          if (call == 2) throw StateError('undecodable page');
          return 'words on $path';
        }),
        repository: repository,
      );

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.done);
      // Every page was attempted; the two that worked were uploaded.
      expect(state.completedPages, 3);
      expect(repository.uploads.single.pages, hasLength(2));
    });

    test('a vanished platform handler stops the run immediately', () async {
      await seedDownloadedChapter();
      final repository = _RecordingOcrRepository();
      final engine = _ScriptedOcrEngine(
        (_) async => throw MissingPluginException('no handler'),
      );
      final container = buildContainer(engine: engine, repository: repository);

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      final state = container.read(ocrRunControllerProvider);
      expect(state.phase, OcrRunPhase.failed);
      expect(state.message, contains('not available'));
      // Stopped on the first page rather than burning the other two proving
      // the same thing.
      expect(engine.recognizedPaths, hasLength(1));
      expect(repository.uploads, isEmpty);
    });
  });

  group('cancellation', () {
    test('cancelling mid-run uploads nothing at all', () async {
      await seedDownloadedChapter();
      final repository = _RecordingOcrRepository();
      late ProviderContainer container;
      final engine = _ScriptedOcrEngine(
        (_) async => 'words',
        onRecognize: (_) {
          // Cancel the moment the first page starts — a half transcript
          // would *replace* a complete one server-side, so "cancelled" has
          // to mean "uploaded nothing".
          container.read(ocrRunControllerProvider.notifier).cancel();
        },
      );
      container = buildContainer(engine: engine, repository: repository);

      await container
          .read(ocrRunControllerProvider.notifier)
          .runChapter(id: _id);

      expect(
        container.read(ocrRunControllerProvider).phase,
        OcrRunPhase.cancelled,
      );
      expect(repository.uploads, isEmpty);
    });

    test('cancelling an idle controller is a no-op', () {
      final container = buildContainer(
        engine: _ScriptedOcrEngine((_) async => 'words'),
        repository: _RecordingOcrRepository(),
        // No store: this test never starts a run, and opening a real
        // database it would not use leaves async work outliving the test.
        withStore: false,
      );

      container.read(ocrRunControllerProvider.notifier).cancel();

      expect(container.read(ocrRunControllerProvider).phase, OcrRunPhase.idle);
    });
  });

  group('foreground gating', () {
    test('backgrounding holds the run, foregrounding finishes it', () async {
      await seedDownloadedChapter();
      final repository = _RecordingOcrRepository();
      late ProviderContainer container;
      var backgroundedOnce = false;
      final engine = _ScriptedOcrEngine(
        (_) async => 'words',
        onRecognize: (_) {
          if (backgroundedOnce) return;
          backgroundedOnce = true;
          container
              .read(ocrRunControllerProvider.notifier)
              .setForeground(false);
        },
      );
      container = buildContainer(engine: engine, repository: repository);

      final controller = container.read(ocrRunControllerProvider.notifier);
      final run = controller.runChapter(id: _id);

      // The run parks between pages rather than racing an app about to
      // suspend, so it has neither finished nor uploaded yet. Polled rather
      // than pumped a fixed number of turns: the store reads real page paths
      // out of a real SQLite database first, which takes an unpredictable
      // number of event-loop turns to resolve.
      await _waitUntil(
        () => container.read(ocrRunControllerProvider).phase ==
            OcrRunPhase.paused,
      );
      expect(repository.uploads, isEmpty);

      controller.setForeground(true);
      await run;

      expect(container.read(ocrRunControllerProvider).phase, OcrRunPhase.done);
      // Nothing recognized before the pause was thrown away.
      expect(repository.uploads.single.pages, hasLength(3));
    });
  });

  test('a second run while one is in flight is refused, not queued', () async {
    await seedDownloadedChapter();
    final repository = _RecordingOcrRepository();
    final completer = Completer<void>();
    final engine = _ScriptedOcrEngine((_) async {
      await completer.future;
      return 'words';
    });
    final container = buildContainer(engine: engine, repository: repository);

    final controller = container.read(ocrRunControllerProvider.notifier);
    final first = controller.runChapter(id: _id);
    await Future<void>.delayed(Duration.zero);
    final second = controller.runChapter(id: _id);

    completer.complete();
    await Future.wait([first, second]);

    // One run, therefore one upload — not two racing the same chapter.
    expect(repository.uploads, hasLength(1));
  });
}
