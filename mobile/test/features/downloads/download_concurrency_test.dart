import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/download_concurrency.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/models/storage_cap.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/retention_maintenance_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_constants.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/services/chapter_page_fetcher.dart';
import 'package:manhwamaniacs/features/downloads/services/device_storage_info.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest_window.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/downloads_test_support.dart';

/// Downloading several chapters at once — the user-facing setting, and the
/// ceiling underneath it.
///
/// The thing under test is not "is it faster". It is that widening the batch
/// changes ONLY how many chapters are in flight, and never any of the
/// properties the serial queue was built around: the free-space floor, the
/// storage cap, pause, cancel and per-chapter retry all still apply per
/// chapter, one chapter's failure is its own, and — the reason a bound exists
/// at all — the number of requests open against the server does not grow with
/// the setting.

const _series = (sourceId: 'asura', seriesKey: 'solo-leveling');

({String sourceId, String seriesKey, String chapterKey}) _id(int n) => (
      sourceId: _series.sourceId,
      seriesKey: _series.seriesKey,
      chapterKey: 'ch-$n',
    );

List<ChapterQueueRequest> _queueRequests(int count) => [
      for (var n = 1; n <= count; n++)
        (
          id: _id(n),
          chapterNumber: n.toDouble(),
          title: null,
          seriesTitle: 'Solo Leveling',
          kind: DownloadKind.manga,
        ),
    ];

/// A reader API that answers one chapter at a time and reports how many of
/// those answers were in flight together.
///
/// Concurrent manifest calls are the cleanest reading of "how many chapters is
/// the loop running": every worker starts with one, so the peak here is the
/// batch width the queue actually chose. The window endpoint deliberately
/// refuses, which sends every chapter down the single-manifest path and keeps
/// that signal readable — the windows themselves are covered in
/// `manifest_window_test.dart`.
class _ChapterCountingReaderRepository implements ReaderRepository {
  _ChapterCountingReaderRepository({
    this.pageCount = 4,
    this.brokenKeys = const <String>{},
    this.onRequest,
  });

  final int pageCount;

  /// Long enough that workers started together are observably in flight
  /// together — without it every manifest resolves inside one microtask turn
  /// and the peak below reads 1 no matter what the queue did.
  final Duration delay = const Duration(milliseconds: 25);

  /// Chapter keys whose manifest never resolves — a permanently broken
  /// chapter, for the failure-isolation case.
  final Set<String> brokenKeys;

  /// Called on entry and exit of every gated call, so a test can watch the
  /// total request count as well as the per-kind one.
  final void Function(int delta)? onRequest;

  int inFlight = 0;
  int maxInFlight = 0;
  final List<String> requested = [];

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) async {
    requested.add(chapterKey);
    inFlight++;
    onRequest?.call(1);
    maxInFlight = inFlight > maxInFlight ? inFlight : maxInFlight;
    await Future<void>.delayed(delay);
    inFlight--;
    onRequest?.call(-1);
    if (brokenKeys.contains(chapterKey)) {
      return const Err(NetworkError(message: 'offline'));
    }
    return Ok(
      ChapterManifest(
        sourceId: sourceId,
        seriesKey: seriesKey,
        chapterKey: chapterKey,
        chapterNumber: double.parse(chapterKey.split('-').last),
        pageCount: pageCount,
        prev: null,
        next: null,
        pages: [
          for (var i = 1; i <= pageCount; i++)
            ManifestPage(
              number: i,
              url: '/sources/asura/pages/$chapterKey-$i/image',
            ),
        ],
      ),
    );
  }

  /// Refused on purpose — see the class doc.
  @override
  Future<Result<ChapterManifestWindow>> manifestWindow({
    required String sourceId,
    required String seriesKey,
    required List<String> chapterKeys,
  }) async =>
      const Err(NetworkError(message: 'no window endpoint here'));

  @override
  Future<Result<ReadingProgress>> saveProgress(ProgressPush push) =>
      throw UnimplementedError();

  @override
  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<BookmarkSyncResult>> syncBookmarks(List<BookmarkOp> ops) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
    DateTime? since,
    bool includeDeleted = false,
    int? limit,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) =>
      throw UnimplementedError();
}

/// Counts concurrent page fetches, and lets a test act at a chosen moment —
/// the seam the cancel-mid-flight and floor-drops-mid-flight cases need.
class _ObservingPageFetcher implements ChapterPageFetcher {
  _ObservingPageFetcher({
    this.delay = const Duration(milliseconds: 20),
    this.onRequest,
    this.onFetch,
  });

  final Duration delay;
  final void Function(int delta)? onRequest;
  final void Function(String url)? onFetch;

  int inFlight = 0;
  int maxInFlight = 0;
  final List<String> requested = [];

  @override
  Future<List<int>> fetchPageBytes(String url) async {
    requested.add(url);
    onFetch?.call(url);
    inFlight++;
    onRequest?.call(1);
    maxInFlight = inFlight > maxInFlight ? inFlight : maxInFlight;
    await Future<void>.delayed(delay);
    inFlight--;
    onRequest?.call(-1);
    return [1, 2, 3, 4];
  }
}

class _FixedStorageCapNotifier extends StorageCapNotifier {
  _FixedStorageCapNotifier(this._cap);
  final StorageCap _cap;

  @override
  StorageCap build() => _cap;
}

class _MutableDeviceStorageInfo implements DeviceStorageInfo {
  _MutableDeviceStorageInfo(this.bytes);
  int? bytes;

  @override
  Future<int?> freeSpaceBytes() async => bytes;
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

  ProviderContainer buildContainer({
    required ReaderRepository readerRepository,
    required ChapterPageFetcher pageFetcher,
    required DownloadConcurrency concurrency,
    DeviceStorageInfo? deviceStorageInfo,
    StorageCap storageCap = StorageCap.unlimited,
  }) {
    final container = ProviderContainer(
      overrides: [
        downloadsStoreProvider.overrideWithValue(harness.storeFor('u1p1')),
        retentionMaintenanceProvider.overrideWithValue(
          RetentionMaintenance(
            database: harness.openDatabase(),
            blobStore: harness.openBlobStore(),
          ),
        ),
        readerRepositoryProvider.overrideWithValue(readerRepository),
        chapterPageFetcherProvider.overrideWithValue(pageFetcher),
        deviceStorageInfoProvider.overrideWithValue(
          deviceStorageInfo ??
              _MutableDeviceStorageInfo(10 * 1024 * 1024 * 1024),
        ),
        storageCapProvider.overrideWith(
          () => _FixedStorageCapNotifier(storageCap),
        ),
        downloadConcurrencyOverride(concurrency),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  group('the setting', () {
    test('round-trips through the app\'s own preferences store', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      SharedPreferences.setMockInitialValues(<String, Object>{});
      final prefs = await SharedPreferences.getInstance();

      final container = ProviderContainer(
        overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      );
      addTearDown(container.dispose);

      // Today's behaviour plus one step, not the maximum.
      expect(
        container.read(downloadConcurrencyProvider),
        DownloadConcurrency.two,
      );

      await container
          .read(downloadConcurrencyProvider.notifier)
          .setConcurrency(DownloadConcurrency.three);
      expect(
        container.read(downloadConcurrencyProvider),
        DownloadConcurrency.three,
      );

      // A relaunch reads it back off the same untyped store every other
      // device-level setting uses — no second storage mechanism.
      final relaunched = ProviderContainer(
        overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
      );
      addTearDown(relaunched.dispose);
      expect(
        relaunched.read(downloadConcurrencyProvider),
        DownloadConcurrency.three,
      );
    });

    test('an unreadable or absent value falls back to the default', () {
      expect(DownloadConcurrency.fromWire(null), DownloadConcurrency.two);
      expect(DownloadConcurrency.fromWire('nine'), DownloadConcurrency.two);
      expect(DownloadConcurrency.one.chapters, 1);
      expect(DownloadConcurrency.three.chapters, 3);
    });
  });

  group('the queue honours it', () {
    test('one chapter at a time on the serial setting', () async {
      final repo = _ChapterCountingReaderRepository();
      final fetcher = _ObservingPageFetcher();
      final container = buildContainer(
        readerRepository: repo,
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.one,
      );

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(4));
      await controller.debugWaitUntilIdle();

      expect(repo.maxInFlight, 1);
      final store = harness.storeFor('u1p1');
      for (var n = 1; n <= 4; n++) {
        expect((await store.getChapter(_id(n)))!.state,
            DownloadChapterState.complete,);
      }
    });

    test('three chapters at a time on the widest setting', () async {
      final repo = _ChapterCountingReaderRepository();
      final fetcher = _ObservingPageFetcher();
      final container = buildContainer(
        readerRepository: repo,
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.three,
      );

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(6));
      await controller.debugWaitUntilIdle();

      expect(repo.maxInFlight, DownloadConcurrency.three.chapters);
      final store = harness.storeFor('u1p1');
      for (var n = 1; n <= 6; n++) {
        expect((await store.getChapter(_id(n)))!.state,
            DownloadChapterState.complete,);
      }
      // Every page of every chapter, fetched exactly once — parallelism must
      // not cost duplicate requests.
      expect(fetcher.requested.length, 6 * 4);
      expect(fetcher.requested.toSet().length, 6 * 4);
    });

    test(
        'the ceiling is the request gate, not the setting times the page '
        'concurrency', () async {
      // The number that actually bounds the blast radius. Three chapters each
      // asking for kPageFetchConcurrency pages is six; the shared gate is what
      // makes the truth four.
      var open = 0;
      var peak = 0;
      void track(int delta) {
        open += delta;
        peak = open > peak ? open : peak;
      }

      final repo = _ChapterCountingReaderRepository(onRequest: track);
      final fetcher = _ObservingPageFetcher(onRequest: track);
      final container = buildContainer(
        readerRepository: repo,
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.three,
      );

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(6));
      await controller.debugWaitUntilIdle();

      expect(peak, lessThanOrEqualTo(kQueueRequestConcurrency));
      expect(
        DownloadConcurrency.three.chapters * kPageFetchConcurrency,
        greaterThan(kQueueRequestConcurrency),
        reason: 'otherwise this test proves nothing about the gate',
      );
      // And it genuinely uses the budget rather than accidentally serialising.
      expect(peak, kQueueRequestConcurrency);
    });
  });

  group('every guard still applies per chapter', () {
    test('the free-space floor stops a whole batch and drops nothing',
        () async {
      final storage = _MutableDeviceStorageInfo(10 * 1024 * 1024 * 1024);
      var fetched = 0;
      final fetcher = _ObservingPageFetcher(
        onFetch: (_) {
          // Fall under the floor once several chapters are already in flight:
          // each worker must notice at its own next chunk boundary.
          if (++fetched == 2) storage.bytes = kFreeSpaceFloorBytes - 1;
        },
      );
      final container = buildContainer(
        readerRepository: _ChapterCountingReaderRepository(pageCount: 12),
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.three,
        deviceStorageInfo: storage,
      );

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(3));
      await controller.debugWaitUntilIdle();

      final state = container.read(downloadQueueControllerProvider);
      expect(state.pauseReason, DownloadQueuePauseReason.freeSpaceFloor);
      expect(state.isDownloading, isFalse);

      final store = harness.storeFor('u1p1');
      for (var n = 1; n <= 3; n++) {
        final chapter = await store.getChapter(_id(n));
        expect(chapter, isNotNull, reason: 'a stopped chapter is never lost');
        expect(chapter!.state, isNot(DownloadChapterState.complete));
      }
    });

    test('the storage cap stops a whole batch and drops nothing', () async {
      final container = buildContainer(
        readerRepository: _ChapterCountingReaderRepository(pageCount: 12),
        pageFetcher: _ObservingPageFetcher(),
        concurrency: DownloadConcurrency.three,
        storageCap: StorageCap.gb2,
      );
      final db = await harness.openDatabase();
      await db.insert('blobs', {
        'hash': 'huge',
        'refcount': 1,
        'size': 3 * 1024 * 1024 * 1024,
      });

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(3));
      await controller.debugWaitUntilIdle();

      expect(container.read(downloadQueueControllerProvider).pauseReason,
          DownloadQueuePauseReason.cap,);
      final store = harness.storeFor('u1p1');
      for (var n = 1; n <= 3; n++) {
        expect((await store.getChapter(_id(n)))!.state,
            DownloadChapterState.queued,);
      }
    });

    test('pause holds every chapter in the batch, resume finishes them all',
        () async {
      late DownloadQueueController controller;
      var pausedOnce = false;
      final fetcher = _ObservingPageFetcher(
        onFetch: (_) {
          if (!pausedOnce) {
            pausedOnce = true;
            controller.pause();
          }
        },
      );
      final container = buildContainer(
        readerRepository: _ChapterCountingReaderRepository(pageCount: 8),
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.three,
      );
      controller = container.read(downloadQueueControllerProvider.notifier);

      await controller.enqueueChapters(_queueRequests(3));
      await controller.debugWaitUntilIdle();

      expect(container.read(downloadQueueControllerProvider).pauseReason,
          DownloadQueuePauseReason.userPaused,);
      final store = harness.storeFor('u1p1');
      for (var n = 1; n <= 3; n++) {
        // Held mid-flight: not dropped, and not falsely completed.
        expect((await store.getChapter(_id(n)))!.state,
            isNot(DownloadChapterState.complete),);
      }
      final beforeResume = fetcher.requested.length;

      controller.resume();
      await controller.debugWaitUntilIdle();

      for (var n = 1; n <= 3; n++) {
        expect((await store.getChapter(_id(n)))!.state,
            DownloadChapterState.complete,);
      }
      // Pages already on disk when the pause landed were never re-fetched.
      expect(fetcher.requested.length, 3 * 8);
      expect(beforeResume, lessThan(3 * 8));
    });
  });

  group('failure and cancellation are per chapter', () {
    test('one broken chapter fails alone; its siblings still complete',
        () async {
      final repo = _ChapterCountingReaderRepository(brokenKeys: {'ch-2'});
      final container = buildContainer(
        readerRepository: repo,
        pageFetcher: _ObservingPageFetcher(),
        concurrency: DownloadConcurrency.three,
      );

      final controller =
          container.read(downloadQueueControllerProvider.notifier);
      await controller.enqueueChapters(_queueRequests(3));
      // ch-2 burns its three manifest retries with a real 2s backoff between
      // them, so this genuinely waits — the point being that ch-1 and ch-3
      // finished long before it gave up.
      await controller.debugWaitUntilIdle();

      final store = harness.storeFor('u1p1');
      expect((await store.getChapter(_id(1)))!.state,
          DownloadChapterState.complete,);
      expect((await store.getChapter(_id(3)))!.state,
          DownloadChapterState.complete,);

      final broken = await store.getChapter(_id(2));
      expect(broken!.state, DownloadChapterState.failed);
      expect(broken.error, isNotNull);
      expect(
        container.read(downloadQueueControllerProvider).pauseReason,
        DownloadQueuePauseReason.none,
        reason: 'one failed chapter must not block the rest of the queue',
      );
    }, timeout: const Timeout(Duration(seconds: 40)),);

    test('a cancel lands cleanly while its siblings are still in flight',
        () async {
      late DownloadQueueController controller;
      Future<void>? cancelling;
      final fetcher = _ObservingPageFetcher(
        delay: const Duration(milliseconds: 30),
        onFetch: (url) {
          // Cancel a chapter that is NOT the one on the progress bar, while
          // the loop still owns its writes — the case the row-id set exists
          // for, since "the current chapter" stopped being the same question
          // as "a chapter the loop is writing".
          if (url.contains('ch-2-')) {
            cancelling ??= controller.cancelChapter(_id(2));
          }
        },
      );
      final container = buildContainer(
        readerRepository: _ChapterCountingReaderRepository(pageCount: 10),
        pageFetcher: fetcher,
        concurrency: DownloadConcurrency.three,
      );
      controller = container.read(downloadQueueControllerProvider.notifier);

      await controller.enqueueChapters(_queueRequests(3));
      await controller.debugWaitUntilIdle();
      await cancelling;
      // The cancel may have landed after that worker finished; either way the
      // loop drains once more before it settles.
      await controller.debugWaitUntilIdle();

      final store = harness.storeFor('u1p1');
      expect(await store.getChapter(_id(2)), isNull);
      expect((await store.getChapter(_id(1)))!.state,
          DownloadChapterState.complete,);
      expect((await store.getChapter(_id(3)))!.state,
          DownloadChapterState.complete,);

      // Nothing the cancelled chapter wrote outlived it: no orphan page rows,
      // and no blob files still held by refcounts that no longer exist.
      final db = await harness.openDatabase();
      final pages = await db.query('saved_pages');
      final liveRowIds = {
        for (final chapter in await store.listChapters()) chapter.rowId,
      };
      for (final page in pages) {
        expect(liveRowIds, contains(page['chapter_rowid']));
      }

      final blobs = await harness.openBlobStore();
      final files = blobs.rootDirectory.existsSync()
          ? blobs.rootDirectory
              .listSync(recursive: true)
              .whereType<File>()
              .length
          : 0;
      final blobRows = await db.query('blobs');
      expect(files, blobRows.length);
    });
  });
}
