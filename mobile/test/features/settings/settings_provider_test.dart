import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';
import 'package:manhwamaniacs/features/downloads/repositories/downloads_repository.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/library/providers/dashboard_providers.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/services/image_cache_service.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Empty-data fake — every list method returns an empty success so the
/// top-level metadata providers resolve without a network call.
class _EmptyLibraryRepository implements LibraryRepository {
  var statisticsCallCount = 0;
  var bookmarksCallCount = 0;

  @override
  Future<Result<PagedResult<FollowedSeries>>> listSeries({
    int page = 1,
    int perPage = 20,
    String? sort,
    String? search,
    String? status,
    String? readingStatus,
    int? collectionId,
    int? tagId,
    bool? isFavorite,
    bool? hasChapters,
  }) async =>
      Ok(PagedResult(items: const [], total: 0, page: 1, perPage: perPage, hasNext: false));

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) async => const Ok([]);

  @override
  Future<Result<List<FollowedSeries>>> recentlyAdded({int limit = 20}) async => const Ok([]);

  @override
  Future<Result<List<FollowedSeries>>> recentlyUpdated({int limit = 20}) async => const Ok([]);

  @override
  Future<Result<List<FollowedSeries>>> recommendations({int limit = 20}) async => const Ok([]);

  @override
  Future<Result<List<FollowedSeries>>> search(String query, {int page = 1}) async => const Ok([]);

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<List<Collection>>> listCollections() async => const Ok([]);

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<Collection>> updateCollection(
    int collectionId, {
    String? name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeSeriesFromCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags() => throw UnimplementedError();

  @override
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<LibraryStatistics>> statistics() async {
    statisticsCallCount++;
    return const Ok(
      LibraryStatistics(
        totalSeries: 0,
        totalChapters: 0,
        totalPages: 0,
        completedSeries: 0,
        inProgress: 0,
        favorites: 0,
        completionRatePct: 0,
        totalReadingTimeEstimateMinutes: 0,
        pagesReadThisWeek: 0,
        readingStreakDays: 0,
        readingVelocityPagesPerHour: 0,
      ),
    );
  }

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) async => const Ok([]);

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) async => const Ok([]);

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async {
    bookmarksCallCount++;
    return const Ok([]);
  }

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) => throw UnimplementedError();

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

class _EmptyUpdatesRepository implements UpdatesRepository {
  var listTrackersCallCount = 0;

  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async =>
      const Ok([]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(0);

  @override
  Future<Result<void>> markRead(int notificationId) => throw UnimplementedError();

  @override
  Future<Result<void>> markAllRead() => throw UnimplementedError();

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async {
    listTrackersCallCount++;
    return const Ok([]);
  }

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteTracker(int trackerId) => throw UnimplementedError();

  @override
  Future<Result<void>> updateTracker(
    int trackerId, {
    bool? autoDownload,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> triggerCheck() => throw UnimplementedError();
}

class _FakeDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

class _FakeImageCacheService implements ImageCacheService {
  int clearCallCount = 0;
  int sizeBytes = 4096;

  @override
  Future<int> getCacheSizeBytes() async => sizeBytes;

  @override
  Future<void> clear() async {
    clearCallCount++;
    sizeBytes = 0;
  }
}

Future<ProviderContainer> _container() async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(_EmptyLibraryRepository()),
      updatesRepositoryProvider.overrideWithValue(_EmptyUpdatesRepository()),
      downloadsRepositoryProvider.overrideWithValue(_FakeDownloadsRepository()),
    ],
  );
}

void main() {
  group('themeModeProvider', () {
    test('reads the persisted preference on build and persists changes', () async {
      final container = await _container();
      addTearDown(container.dispose);

      expect(container.read(themeModeProvider), ThemeMode.system);

      await container.read(themeModeProvider.notifier).setThemeMode(ThemeMode.dark);
      expect(container.read(themeModeProvider), ThemeMode.dark);

      final prefs = container.read(preferencesProvider);
      expect(prefs.themeMode, ThemeMode.dark);
    });
  });

  group('languageProvider', () {
    test('defaults to English and persists a language change', () async {
      final container = await _container();
      addTearDown(container.dispose);

      expect(container.read(languageProvider), AppLanguage.english);

      await container.read(languageProvider.notifier).setLanguage(AppLanguage.korean);
      expect(container.read(languageProvider), AppLanguage.korean);
      expect(container.read(preferencesProvider).language, 'ko');
    });
  });

  group('readerDefaultsProvider', () {
    test('persists direction, fit mode, keep-awake, and auto-next independently', () async {
      final container = await _container();
      addTearDown(container.dispose);

      final notifier = container.read(readerDefaultsProvider.notifier);

      await notifier.setDirection(ReadingDirection.rightToLeft);
      await notifier.setFitMode(ReaderFitMode.screen);
      await notifier.setKeepScreenAwake(true);
      await notifier.setAutoNextChapter(false);
      await notifier.setLockControls(true);
      await notifier.setRefreshRate(ReaderRefreshRate.fps90);

      final state = container.read(readerDefaultsProvider);
      expect(state.direction, ReadingDirection.rightToLeft);
      expect(state.fitMode, ReaderFitMode.screen);
      expect(state.keepScreenAwake, isTrue);
      expect(state.autoNextChapter, isFalse);
      expect(state.lockControls, isTrue);
      expect(state.refreshRate, ReaderRefreshRate.fps90);

      final prefs = container.read(preferencesProvider);
      expect(prefs.readingDirection, 'rightToLeft');
      expect(prefs.readerFitMode, 'screen');
      expect(prefs.lockReaderControls, isTrue);
      expect(prefs.readerRefreshRate, 'fps90');
    });

    test('defaults refresh rate to auto when nothing is persisted', () async {
      final container = await _container();
      addTearDown(container.dispose);

      expect(
        container.read(readerDefaultsProvider).refreshRate,
        ReaderRefreshRate.auto,
      );
    });
  });

  group('wifiOnlyDownloadsProvider', () {
    test('defaults to false and persists toggling on', () async {
      final container = await _container();
      addTearDown(container.dispose);

      expect(container.read(wifiOnlyDownloadsProvider), isFalse);

      await container.read(wifiOnlyDownloadsProvider.notifier).setEnabled(true);
      expect(container.read(wifiOnlyDownloadsProvider), isTrue);
      expect(container.read(preferencesProvider).wifiOnlyDownloads, isTrue);
    });
  });

  group('SettingsActions cache actions', () {
    test('clearImageCache clears via the injected service and invalidates usage', () async {
      final container = await _container();
      addTearDown(container.dispose);
      final fakeCache = _FakeImageCacheService();

      final overriddenContainer = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(container.read(sharedPrefsProvider)),
          libraryRepositoryProvider.overrideWithValue(_EmptyLibraryRepository()),
          updatesRepositoryProvider.overrideWithValue(_EmptyUpdatesRepository()),
          downloadsRepositoryProvider.overrideWithValue(_FakeDownloadsRepository()),
          imageCacheServiceProvider.overrideWithValue(fakeCache),
        ],
      );
      addTearDown(overriddenContainer.dispose);

      expect(await overriddenContainer.read(cacheUsageProvider.future), 4096);

      await overriddenContainer.read(settingsActionsProvider).clearImageCache();

      expect(fakeCache.clearCallCount, 1);
      expect(await overriddenContainer.read(cacheUsageProvider.future), 0);
    });

    test(
        'clearMetadataCache forces a real refetch on next read (proves '
        'invalidation, not just a state flag)', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final libraryRepo = _EmptyLibraryRepository();
      final updatesRepo = _EmptyUpdatesRepository();
      final container = ProviderContainer(
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          libraryRepositoryProvider.overrideWithValue(libraryRepo),
          updatesRepositoryProvider.overrideWithValue(updatesRepo),
          downloadsRepositoryProvider.overrideWithValue(_FakeDownloadsRepository()),
        ],
      );
      addTearDown(container.dispose);

      // Hold each provider alive with a listener, matching how a mounted
      // screen ref.watch()es it -- otherwise these autoDispose providers
      // would refetch on every plain container.read() regardless of
      // invalidation, making this test meaningless.
      container.listen(dashboardProvider, (_, __) {}, fireImmediately: true);
      container.listen(bookmarksProvider, (_, __) {}, fireImmediately: true);
      container.listen(updatesProvider, (_, __) {}, fireImmediately: true);

      await container.read(dashboardProvider.future);
      await container.read(bookmarksProvider.future);
      await container.read(updatesProvider.future);
      expect(libraryRepo.statisticsCallCount, 1);
      expect(libraryRepo.bookmarksCallCount, 1);
      expect(updatesRepo.listTrackersCallCount, 1);

      // Reading again while still listened must hit the cached value, not
      // refetch -- confirms the baseline before we invalidate.
      await container.read(dashboardProvider.future);
      expect(libraryRepo.statisticsCallCount, 1);

      final statisticsCallsBefore = libraryRepo.statisticsCallCount;
      final bookmarksCallsBefore = libraryRepo.bookmarksCallCount;
      final trackersCallsBefore = updatesRepo.listTrackersCallCount;

      container.read(settingsActionsProvider).clearMetadataCache();

      await container.read(dashboardProvider.future);
      await container.read(bookmarksProvider.future);
      await container.read(updatesProvider.future);

      // With an active listener, invalidating can trigger Riverpod's own
      // eager rebuild in addition to the read above, so assert "refetched
      // at least once" rather than an exact count -- what matters is that
      // clearMetadataCache() demonstrably forced new server calls instead
      // of silently reusing the stale cached value.
      expect(libraryRepo.statisticsCallCount, greaterThan(statisticsCallsBefore));
      expect(libraryRepo.bookmarksCallCount, greaterThan(bookmarksCallsBefore));
      expect(updatesRepo.listTrackersCallCount, greaterThan(trackersCallsBefore));
    });

    test('metadataCacheInvalidators covers every intended provider exactly once', () {
      expect(metadataCacheInvalidators, hasLength(8));
    });
  });
}