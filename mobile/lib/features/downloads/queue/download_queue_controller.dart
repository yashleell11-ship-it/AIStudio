import 'dart:async';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/retention_maintenance_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_constants.dart';
import 'package:manhwamaniacs/features/downloads/services/chapter_page_fetcher.dart';
import 'package:manhwamaniacs/features/downloads/services/device_storage_info.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// Why the queue isn't actively fetching right now.
enum DownloadQueuePauseReason {
  /// Nothing queued, or actively downloading.
  none,

  /// No active `(user, profile)` session — nothing to download into.
  noScope,

  /// Sideloaded iOS (and this app generally) has no dependable background
  /// execution — see `docs/OFFLINE_READING.md` "Known limitation". The queue
  /// resumes automatically the moment the app is foregrounded again.
  backgrounded,

  /// The ~1.5 GB free-space floor — independent of the user's cap, always
  /// enforced.
  freeSpaceFloor,

  /// The user's configured storage cap.
  cap,

  /// The user tapped Pause. The only reason that survives backgrounding and
  /// relaunch-free resumes untouched — every other one clears itself as soon
  /// as its condition lifts, and this one must not.
  userPaused,
}

class DownloadQueueState {
  const DownloadQueueState({
    this.isDownloading = false,
    this.pauseReason = DownloadQueuePauseReason.none,
    this.currentChapter,
    this.pagesDone = 0,
    this.pageTotal = 0,
    this.queueRevision = 0,
  });

  /// True only while a page fetch is actually in flight — distinct from
  /// "has queued work", which the Downloads screen reads straight from the
  /// store instead (queued rows persist across app restarts; this flag does
  /// not).
  final bool isDownloading;
  final DownloadQueuePauseReason pauseReason;
  final ChapterIdentity? currentChapter;

  /// Pages of [currentChapter] already on disk, and how many it has in total.
  /// Both zero when nothing is downloading. [pageTotal] is 0 until the
  /// manifest lands, which is exactly the window where the UI should show an
  /// indeterminate bar rather than a misleading "0 of 0".
  final int pagesDone;
  final int pageTotal;

  /// Bumped on every change to *which rows exist and in what state* — a
  /// chapter queued, completed, failed or cancelled — and deliberately **not**
  /// on page-by-page progress.
  ///
  /// The store-backed providers (the downloads list, the per-series
  /// breakdown, the device byte total) re-query on this rather than on the
  /// whole state, so a 40-page chapter costs them one refresh instead of
  /// forty. Widgets that want the live page counter watch the state itself.
  final int queueRevision;

  bool get isPaused => pauseReason != DownloadQueuePauseReason.none;

  /// True when the pause is something the user can act on from the Downloads
  /// screen, as opposed to a transient state the queue clears by itself.
  bool get isBlocked =>
      pauseReason == DownloadQueuePauseReason.cap ||
      pauseReason == DownloadQueuePauseReason.freeSpaceFloor ||
      pauseReason == DownloadQueuePauseReason.userPaused;

  DownloadQueueState copyWith({
    bool? isDownloading,
    DownloadQueuePauseReason? pauseReason,
    ChapterIdentity? currentChapter,
    bool clearCurrentChapter = false,
    int? pagesDone,
    int? pageTotal,
    int? queueRevision,
  }) {
    return DownloadQueueState(
      isDownloading: isDownloading ?? this.isDownloading,
      pauseReason: pauseReason ?? this.pauseReason,
      currentChapter:
          clearCurrentChapter ? null : (currentChapter ?? this.currentChapter),
      pagesDone: pagesDone ?? this.pagesDone,
      pageTotal: pageTotal ?? this.pageTotal,
      queueRevision: queueRevision ?? this.queueRevision,
    );
  }
}

enum _ChapterOutcome {
  completed,
  failed,
  cancelled,
  pausedFloor,
  pausedCap,
  pausedUser,
}

/// The foreground-only download queue engine (spec §3): fetch manifest,
/// fetch pages at concurrency [kPageFetchConcurrency], write blobs, resume by
/// skipping pages already on disk, bounded retry, and hard-stop at the
/// free-space floor / storage cap without ever dropping a queued chapter or
/// touching an unread one.
///
/// A durable queue, not an in-memory one: every "queued" row lives in
/// `saved_chapters` the instant [enqueueChapter] returns, so a kill mid-run
/// loses at most the current page — never the fact that a chapter was asked
/// for. [resumePendingOnLaunch] re-discovers that work on the next start.
///
/// Deliberately operates on whichever store `downloadsStoreProvider` reports
/// *right now* on every loop pass, rather than a store captured once: a
/// profile switch mid-download simply pauses that profile's queue (its rows
/// stay `queued`/`downloading`, resumed next time that profile — or a fresh
/// launch — reaches it) rather than juggling two profiles' fetches at once.
class DownloadQueueController extends Notifier<DownloadQueueState> {
  bool _foreground = true;
  bool _userPaused = false;
  bool _loopRunning = false;
  Future<void>? _activeRun;

  /// Row ids the user cancelled while the loop still owned their writes. See
  /// [cancelChapter] for why the deletion is deferred to the loop.
  final Set<int> _cancelledRowIds = {};

  /// Awaits the current processing pass, if one is running — **test-only**.
  /// Production callers must never await the queue draining: `enqueueChapter`
  /// et al. are deliberately fire-and-forget so the UI stays responsive while
  /// the reactive [DownloadQueueState] reports progress.
  @visibleForTesting
  Future<void> debugWaitUntilIdle() => _activeRun ?? Future<void>.value();

  @override
  DownloadQueueState build() => const DownloadQueueState();

  /// Marks a chapter for download and (re)starts the loop if it was idle.
  /// A no-op with no active scope — the caller's UI should already be
  /// hiding the download affordance in that case.
  Future<void> enqueueChapter({
    required ChapterIdentity id,
    double? chapterNumber,
    String? title,
    String? seriesTitle,
  }) async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    await store.ensureQueued(
      id: id,
      chapterNumber: chapterNumber,
      title: title,
      seriesTitle: seriesTitle,
    );
    _bumpRevision();
    unawaited(_kick());
  }

  /// Queues every chapter in [chapters] — "Download series". Sequential
  /// `await`s rather than `Future.wait`: each call is a single fast insert,
  /// and running them one at a time keeps insertion order equal to queue
  /// order (`created_at`).
  ///
  /// One revision bump for the whole batch, not one per chapter: queueing a
  /// 200-chapter series must cost the store-backed lists a single refresh.
  Future<void> enqueueChapters(Iterable<ChapterQueueRequest> chapters) async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    for (final chapter in chapters) {
      await store.ensureQueued(
        id: chapter.id,
        chapterNumber: chapter.chapterNumber,
        title: chapter.title,
        seriesTitle: chapter.seriesTitle,
      );
    }
    _bumpRevision();
    unawaited(_kick());
  }

  /// Resets a failed chapter to `queued` and restarts the loop.
  /// `ensureQueued` already implements the reset — same call, named for the
  /// UI's "Retry" affordance.
  Future<void> retryChapter(ChapterIdentity id) => enqueueChapter(id: id);

  /// Re-discovers any `queued`/`downloading` rows left over from a previous
  /// run (a kill mid-chapter, or the app simply being closed) and resumes
  /// them. Safe to call repeatedly (a no-op once nothing is pending).
  void resumePendingOnLaunch() => unawaited(_kick());

  /// Holds the queue until [resume]. Queued rows are untouched — this is a
  /// pause, never a cancel — and the chapter mid-flight stops at its next
  /// page-chunk boundary with everything already fetched left on disk.
  void pause() {
    if (_userPaused) return;
    _userPaused = true;
    state = state.copyWith(
      isDownloading: false,
      pauseReason: DownloadQueuePauseReason.userPaused,
    );
  }

  void resume() {
    if (!_userPaused) return;
    _userPaused = false;
    state = state.copyWith(pauseReason: DownloadQueuePauseReason.none);
    unawaited(_kick());
  }

  /// Drops [id] from the queue and removes whatever it had already written.
  ///
  /// Cancelling the chapter the loop is *currently* fetching cannot delete
  /// its rows here: pages already in flight would insert `saved_pages` rows
  /// pointing at a chapter row that no longer exists, leaking the blob
  /// refcounts those rows hold. So that case is flagged and the loop performs
  /// the deletion itself the moment its current page chunk lands.
  Future<void> cancelChapter(ChapterIdentity id) async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    final chapter = await store.getChapter(id);
    if (chapter == null) return;

    if (_loopRunning && state.currentChapter == id) {
      _cancelledRowIds.add(chapter.rowId);
      _bumpRevision();
      return;
    }
    await store.deleteDownload(id);
    _bumpRevision();
  }

  /// Clears every chapter that is queued, mid-download or failed. Completed
  /// downloads are untouched — this empties the queue, it does not delete the
  /// user's library.
  Future<void> cancelAll() async {
    final store = ref.read(downloadsStoreProvider);
    if (store == null) return;
    for (final chapter in await store.unfinishedChapters()) {
      await cancelChapter(chapter.identity);
    }
  }

  /// Toggled by the app-lifecycle gate. Backgrounding pauses the loop before
  /// its next network call; foregrounding restarts it — unless the user
  /// paused it by hand, which outlives a trip to the home screen.
  void setForeground(bool foreground) {
    if (_foreground == foreground) return;
    _foreground = foreground;
    if (foreground) {
      if (_userPaused) return;
      unawaited(_kick());
    } else {
      if (_userPaused) return;
      state = state.copyWith(
        isDownloading: false,
        pauseReason: DownloadQueuePauseReason.backgrounded,
      );
    }
  }

  void _bumpRevision() =>
      state = state.copyWith(queueRevision: state.queueRevision + 1);

  Future<void> _kick() {
    if (_loopRunning) return _activeRun ?? Future<void>.value();
    _loopRunning = true;
    final run = _processLoop().whenComplete(() => _loopRunning = false);
    _activeRun = run;
    return run;
  }

  Future<void> _processLoop() async {
    while (true) {
      if (_userPaused) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.userPaused,
        );
        return;
      }

      if (!_foreground) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.backgrounded,
          clearCurrentChapter: true,
        );
        return;
      }

      final store = ref.read(downloadsStoreProvider);
      if (store == null) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.noScope,
          clearCurrentChapter: true,
        );
        return;
      }

      final pending = await store.pendingChapters();
      if (pending.isEmpty) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.none,
          clearCurrentChapter: true,
          pagesDone: 0,
          pageTotal: 0,
        );
        return;
      }

      final floorBlocked = await _isBelowFreeSpaceFloor();
      if (floorBlocked) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.freeSpaceFloor,
        );
        return;
      }

      final capBlocked = await _isAtOrOverCap();
      if (capBlocked) {
        state = state.copyWith(
          isDownloading: false,
          pauseReason: DownloadQueuePauseReason.cap,
        );
        return;
      }

      final chapter = pending.first;
      state = state.copyWith(
        isDownloading: true,
        pauseReason: DownloadQueuePauseReason.none,
        currentChapter: chapter.identity,
        pagesDone: 0,
        pageTotal: chapter.pageCount,
      );

      final outcome = await _downloadOneChapter(store, chapter);

      // A cancel that landed while this chapter was in flight is honoured
      // whatever the outcome was — including a chapter that finished a
      // moment too late to notice it had been cancelled.
      if (_cancelledRowIds.remove(chapter.rowId)) {
        await store.deleteDownload(chapter.identity);
        _bumpRevision();
        continue;
      }

      switch (outcome) {
        case _ChapterOutcome.pausedFloor:
          state = state.copyWith(
            isDownloading: false,
            pauseReason: DownloadQueuePauseReason.freeSpaceFloor,
          );
          return;
        case _ChapterOutcome.pausedCap:
          state = state.copyWith(
            isDownloading: false,
            pauseReason: DownloadQueuePauseReason.cap,
          );
          return;
        case _ChapterOutcome.pausedUser:
          state = state.copyWith(
            isDownloading: false,
            pauseReason: DownloadQueuePauseReason.userPaused,
          );
          return;
        case _ChapterOutcome.completed:
        case _ChapterOutcome.failed:
        case _ChapterOutcome.cancelled:
          // The row's state changed on disk; the store-backed lists need to
          // re-read. Loop around to the next pending chapter.
          _bumpRevision();
      }
    }
  }

  Future<bool> _isBelowFreeSpaceFloor() async {
    final free = await ref.read(deviceStorageInfoProvider).freeSpaceBytes();
    // Undeterminable free space fails open — see DeviceStorageInfo's doc
    // comment: refusing to ever download without a working platform channel
    // would be a worse failure mode than the rare case this floor exists to
    // prevent.
    if (free == null) return false;
    return free < kFreeSpaceFloorBytes;
  }

  Future<bool> _isAtOrOverCap() async {
    final cap = ref.read(storageCapProvider).bytes;
    if (cap == null) return false; // StorageCap.unlimited
    final used = await ref.read(retentionMaintenanceProvider).totalDeviceBytes();
    return used >= cap;
  }

  /// Fetches the manifest, fetches every page not already on disk, and marks
  /// the chapter complete once every page is present. The manifest is always
  /// re-fetched — including on a resumed chapter whose page count is already
  /// known — because manifest page URLs can carry short-lived signed-proxy
  /// query parameters; a copy cached from before an app kill is not
  /// trustworthy for a fresh fetch, only [DownloadsStore.existingPageNumbers]
  /// (what's already safely on disk) is.
  Future<_ChapterOutcome> _downloadOneChapter(
    DownloadsStore store,
    SavedChapter chapter,
  ) async {
    if (_cancelledRowIds.contains(chapter.rowId)) {
      return _ChapterOutcome.cancelled;
    }

    final manifestResult = await ref.read(readerRepositoryProvider).manifest(
          sourceId: chapter.sourceId,
          seriesKey: chapter.seriesKey,
          chapterKey: chapter.chapterKey,
        );
    if (manifestResult.isErr) {
      return _recordChapterFailure(store, chapter, manifestResult.error.userMessage);
    }
    final manifest = manifestResult.value;
    if (manifest.pageCount <= 0 || manifest.pages.isEmpty) {
      return _recordChapterFailure(store, chapter, 'This chapter has no pages.');
    }

    await store.updateManifestInfo(
      rowId: chapter.rowId,
      pageCount: manifest.pageCount,
      chapterNumber: manifest.chapterNumber,
    );

    final pauseOutcome = await _fetchMissingPages(
      store,
      chapter.rowId,
      pages: manifest.pages,
    );
    if (pauseOutcome != null) return pauseOutcome;

    final completed = await store.markCompleteIfAllPagesPresent(chapter.rowId);
    if (completed) return _ChapterOutcome.completed;
    // One or more pages exhausted their own bounded retries — the chapter
    // itself still needs a bound, or a permanently-broken page would leave
    // this chapter `downloading` forever, re-picked by every loop pass.
    return _recordChapterFailure(
      store,
      chapter,
      'Some pages failed to download.',
    );
  }

  /// Bounded retry at the chapter level: increments `retry_count` and, once
  /// [kMaxChapterManifestRetries] is reached, marks the chapter
  /// [DownloadChapterState.failed] with [error] — visible on the Downloads
  /// screen with a retry action, never silently dropped. Below the bound, a
  /// short backoff runs before returning so a broken chapter can't spin the
  /// loop tight; the row itself is left as-is (still `queued`/`downloading`)
  /// so the next pass picks it back up.
  Future<_ChapterOutcome> _recordChapterFailure(
    DownloadsStore store,
    SavedChapter chapter,
    String error,
  ) async {
    await store.incrementRetry(chapter.rowId);
    final updated = await store.getChapter(chapter.identity);
    final retryCount = updated?.retryCount ?? kMaxChapterManifestRetries;
    if (retryCount >= kMaxChapterManifestRetries) {
      await store.markFailed(rowId: chapter.rowId, error: error);
      return _ChapterOutcome.failed;
    }
    await Future<void>.delayed(kChapterRetryBackoff);
    return _ChapterOutcome.failed;
  }

  /// Fetches every page in [pages] not already on disk, [kPageFetchConcurrency]
  /// at a time, re-checking the free-space floor, the storage cap, a user
  /// pause and a cancel between chunks so a single oversized chapter can
  /// genuinely stop mid-download. Returns a stop outcome when it had to bail
  /// early, or `null` to mean "kept going / finished" — the caller then checks
  /// page completeness.
  Future<_ChapterOutcome?> _fetchMissingPages(
    DownloadsStore store,
    int rowId, {
    required List<ManifestPage> pages,
  }) async {
    final already = await store.existingPageNumbers(rowId);
    final missing = pages.where((p) => !already.contains(p.number)).toList();
    // A resumed chapter starts partway along the bar rather than at zero.
    var done = pages.length - missing.length;
    _reportPageProgress(done: done, total: pages.length);

    for (var i = 0; i < missing.length; i += kPageFetchConcurrency) {
      if (_cancelledRowIds.contains(rowId)) return _ChapterOutcome.cancelled;
      if (_userPaused) return _ChapterOutcome.pausedUser;
      if (await _isBelowFreeSpaceFloor()) return _ChapterOutcome.pausedFloor;
      if (await _isAtOrOverCap()) return _ChapterOutcome.pausedCap;

      final chunk = missing.skip(i).take(kPageFetchConcurrency);
      await Future.wait(
        chunk.map((page) async {
          final saved = await _fetchOnePageWithRetry(
            store,
            rowId,
            number: page.number,
            url: page.url,
          );
          // Only a page actually on disk moves the bar — a page that
          // exhausted its retries must not read as progress.
          if (saved) _reportPageProgress(done: ++done, total: pages.length);
        }),
      );
    }
    return null;
  }

  void _reportPageProgress({required int done, required int total}) {
    state = state.copyWith(pagesDone: done, pageTotal: total);
  }

  /// Returns whether the page ended up on disk.
  Future<bool> _fetchOnePageWithRetry(
    DownloadsStore store,
    int rowId, {
    required int number,
    required String url,
  }) async {
    for (var attempt = 1; attempt <= kMaxPageRetries; attempt++) {
      try {
        final bytes =
            await ref.read(chapterPageFetcherProvider).fetchPageBytes(url);
        if (bytes.isEmpty) throw StateError('Empty page response');
        await store.savePage(rowId: rowId, pageNumber: number, bytes: bytes);
        return true;
      } catch (_) {
        if (attempt >= kMaxPageRetries) return false; // leaves the page missing;
        // markCompleteIfAllPagesPresent will correctly refuse to complete,
        // so the chapter is retried (not silently marked done) next pass.
        await Future<void>.delayed(kPageRetryBackoff);
      }
    }
    return false;
  }
}

/// One chapter to enqueue — the shape `enqueueChapters` (from a "Download
/// series" action) takes, since the store itself has no way to learn a
/// connector's chapter list.
typedef ChapterQueueRequest = ({
  ChapterIdentity id,
  double? chapterNumber,
  String? title,
  String? seriesTitle,
});

final downloadQueueControllerProvider =
    NotifierProvider<DownloadQueueController, DownloadQueueState>(
  DownloadQueueController.new,
  name: 'downloadQueueController',
);
