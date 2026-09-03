import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
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
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/repositories/reader_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

import '../../support/downloads_test_support.dart';

const _id = (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: 'c1');

/// A [ReaderRepository] whose `manifest()` behaviour is fully scripted —
/// letting a test simulate a flaky or permanently-broken chapter without a
/// real network.
class _ScriptedReaderRepository implements ReaderRepository {
  _ScriptedReaderRepository(this._manifest);

  final Future<Result<ChapterManifest>> Function() _manifest;
  int calls = 0;

  @override
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  }) {
    calls++;
    return _manifest();
  }

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
  Future<Result<Bookmark>> addBookmark({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) =>
      throw UnimplementedError();
}

ChapterManifest _manifestWithPages(int pageCount) => ChapterManifest(
      sourceId: _id.sourceId,
      seriesKey: _id.seriesKey,
      chapterKey: _id.chapterKey,
      chapterNumber: 1,
      pageCount: pageCount,
      prev: null,
      next: null,
      pages: [
        for (var i = 1; i <= pageCount; i++)
          ManifestPage(number: i, url: '/sources/asura/pages/$i/image'),
      ],
    );

/// A [ChapterPageFetcher] whose behaviour per URL is fully scripted.
class _ScriptedPageFetcher implements ChapterPageFetcher {
  _ScriptedPageFetcher(this._fetch, {this.onFetch});

  final Future<List<int>> Function(String url) _fetch;
  final void Function(String url)? onFetch;

  @override
  Future<List<int>> fetchPageBytes(String url) {
    onFetch?.call(url);
    return _fetch(url);
  }
}

class _FixedDeviceStorageInfo implements DeviceStorageInfo {
  _FixedDeviceStorageInfo(this.bytes);
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
          deviceStorageInfo ?? _FixedDeviceStorageInfo(10 * 1024 * 1024 * 1024),
        ),
        storageCapProvider.overrideWith(
          () => _FixedStorageCapNotifier(storageCap),
        ),
      ],
    );
    addTearDown(container.dispose);
    return container;
  }

  test('downloads every page and marks the chapter complete', () async {
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(3)),
      ),
      pageFetcher: _ScriptedPageFetcher((url) async => [1, 2, 3]),
    );

    final controller = container.read(downloadQueueControllerProvider.notifier);
    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();

    final store = harness.storeFor('u1p1');
    final chapter = await store.getChapter(_id);
    expect(chapter!.state, DownloadChapterState.complete);
    expect(chapter.pageCount, 3);

    final state = container.read(downloadQueueControllerProvider);
    expect(state.isDownloading, isFalse);
    expect(state.pauseReason, DownloadQueuePauseReason.none);
  });

  test('resumes only the missing pages after a simulated kill mid-chapter',
      () async {
    final store = harness.storeFor('u1p1');
    final rowId = await store.ensureQueued(id: _id);
    await store.updateManifestInfo(rowId: rowId, pageCount: 3);
    await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1]);
    // Page 2 and 3 never landed — simulating an app kill.

    final requestedUrls = <String>[];
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(3)),
      ),
      pageFetcher: _ScriptedPageFetcher(
        (url) async => [9],
        onFetch: requestedUrls.add,
      ),
    );

    final controller = container.read(downloadQueueControllerProvider.notifier);
    controller.resumePendingOnLaunch();
    await controller.debugWaitUntilIdle();

    // Only pages 2 and 3 should ever have been requested — page 1 was
    // already on disk.
    expect(requestedUrls, hasLength(2));
    expect(requestedUrls.any((u) => u.contains('/1/image')), isFalse);

    final resumedStore = harness.storeFor('u1p1');
    expect((await resumedStore.getChapter(_id))!.state,
        DownloadChapterState.complete);
  });

  test('fetches at most kPageFetchConcurrency pages at once', () async {
    var inFlight = 0;
    var maxInFlight = 0;
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(6)),
      ),
      pageFetcher: _ScriptedPageFetcher((url) async {
        inFlight++;
        maxInFlight = inFlight > maxInFlight ? inFlight : maxInFlight;
        await Future<void>.delayed(const Duration(milliseconds: 20));
        inFlight--;
        return [1];
      }),
    );

    final controller = container.read(downloadQueueControllerProvider.notifier);
    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();

    expect(maxInFlight, lessThanOrEqualTo(kPageFetchConcurrency));
    expect(maxInFlight, greaterThan(0));
  });

  test(
      'bounded retry: a permanently-broken manifest is marked failed, not '
      'retried forever', () async {
    final repo = _ScriptedReaderRepository(
      () async => const Err(NetworkError(message: 'offline')),
    );
    final container = buildContainer(
      readerRepository: repo,
      pageFetcher: _ScriptedPageFetcher((url) async => [1]),
    );

    final controller = container.read(downloadQueueControllerProvider.notifier);
    await controller.enqueueChapter(id: _id);
    // 3 retries with a real 2s backoff between them — fake_async/clock
    // control isn't wired up here, so this genuinely waits.
    await controller.debugWaitUntilIdle();

    expect(repo.calls, kMaxChapterManifestRetries);
    final store = harness.storeFor('u1p1');
    final chapter = await store.getChapter(_id);
    expect(chapter!.state, DownloadChapterState.failed);
    expect(chapter.error, isNotNull);

    final state = container.read(downloadQueueControllerProvider);
    expect(state.pauseReason, DownloadQueuePauseReason.none,
        reason: 'a failed chapter must not block the rest of the queue');
  }, timeout: const Timeout(Duration(seconds: 15)));

  test('retrying a failed chapter resets it and downloads successfully',
      () async {
    var shouldFail = true;
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(() async {
        if (shouldFail) return const Err(NetworkError(message: 'offline'));
        return Ok(_manifestWithPages(1));
      }),
      pageFetcher: _ScriptedPageFetcher((url) async => [1]),
    );
    final controller = container.read(downloadQueueControllerProvider.notifier);

    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();
    final store = harness.storeFor('u1p1');
    expect((await store.getChapter(_id))!.state, DownloadChapterState.failed);

    shouldFail = false;
    await controller.retryChapter(_id);
    await controller.debugWaitUntilIdle();

    expect((await store.getChapter(_id))!.state, DownloadChapterState.complete);
  }, timeout: const Timeout(Duration(seconds: 15)));

  test('pauses at the free-space floor without dropping the queued chapter',
      () async {
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(2)),
      ),
      pageFetcher: _ScriptedPageFetcher((url) async => [1]),
      deviceStorageInfo: _FixedDeviceStorageInfo(kFreeSpaceFloorBytes - 1),
    );

    final controller = container.read(downloadQueueControllerProvider.notifier);
    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();

    final state = container.read(downloadQueueControllerProvider);
    expect(state.pauseReason, DownloadQueuePauseReason.freeSpaceFloor);
    expect(state.isDownloading, isFalse);

    // The chapter was never even started — still queued, not dropped.
    final store = harness.storeFor('u1p1');
    expect((await store.getChapter(_id))!.state, DownloadChapterState.queued);
  });

  test('pauses at the storage cap without dropping the queued chapter',
      () async {
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(2)),
      ),
      pageFetcher: _ScriptedPageFetcher((url) async => [1]),
      storageCap: StorageCap.gb2,
    );
    // Force totalDeviceBytes() (via the harness's real db) above the 2 GB cap
    // by inserting an oversized blob row directly.
    final db = await harness.openDatabase();
    await db.insert('blobs', {
      'hash': 'huge',
      'refcount': 1,
      'size': 3 * 1024 * 1024 * 1024,
    });

    final controller = container.read(downloadQueueControllerProvider.notifier);
    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();

    final state = container.read(downloadQueueControllerProvider);
    expect(state.pauseReason, DownloadQueuePauseReason.cap);

    final store = harness.storeFor('u1p1');
    expect((await store.getChapter(_id))!.state, DownloadChapterState.queued);
  });

  test('a backgrounded app pauses the queue instead of downloading', () async {
    var fetchCount = 0;
    final container = buildContainer(
      readerRepository: _ScriptedReaderRepository(
        () async => Ok(_manifestWithPages(2)),
      ),
      pageFetcher: _ScriptedPageFetcher((url) async {
        fetchCount++;
        return [1];
      }),
    );
    final controller = container.read(downloadQueueControllerProvider.notifier);
    controller.setForeground(false);

    await controller.enqueueChapter(id: _id);
    await controller.debugWaitUntilIdle();

    expect(fetchCount, 0);
    expect(container.read(downloadQueueControllerProvider).pauseReason,
        DownloadQueuePauseReason.backgrounded);

    controller.setForeground(true);
    await controller.debugWaitUntilIdle();

    expect(fetchCount, 2);
  });
}

class _FixedStorageCapNotifier extends StorageCapNotifier {
  _FixedStorageCapNotifier(this._cap);
  final StorageCap _cap;

  @override
  StorageCap build() => _cap;
}
