import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
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
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/reading_history_screen.dart';
import 'package:manhwamaniacs/features/library/screens/recommendations_screen.dart';
import 'package:manhwamaniacs/features/library/screens/statistics_screen.dart';
import 'package:manhwamaniacs/features/more/screens/more_screen.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/settings/models/app_version.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/settings_screen.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_pin.dart';
import 'package:manhwamaniacs/features/sources/models/source_search_group.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/features/sources/screens/sources_list_screen.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/repositories/updates_repository.dart';
import 'package:manhwamaniacs/features/updates/screens/updates_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/test_overrides.dart';

FollowedSeries _series({required int id, required String title}) {
  return FollowedSeries(
    id: id,
    libraryId: 1,
    title: title,
    sortTitle: title.toLowerCase(),
    contentRating: 'teen',
    language: 'en',
    folderPath: '/library/$title',
    isFavorite: false,
    readingStatus: 'reading',
    chapterCount: 10,
    readChapters: 2,
    pageCount: 200,
    totalChapters: 10,
    totalPages: 200,
    createdAt: DateTime(2024),
    updatedAt: DateTime(2024, 6),
  );
}

class _FakeIntelligenceRepository implements LibraryRepository {
  @override
  Future<Result<List<FollowedSeries>>> recommendations({int limit = 20}) async =>
      Ok([_series(id: 1, title: 'Recommended Title')]);

  @override
  Future<Result<LibraryStatistics>> statistics() async => const Ok(
        LibraryStatistics(
          totalSeries: 10,
          totalChapters: 100,
          totalPages: 2000,
          completedSeries: 2,
          inProgress: 3,
          favorites: 1,
          completionRatePct: 20,
          totalReadingTimeEstimateMinutes: 600,
          pagesReadThisWeek: 40,
          readingStreakDays: 2,
          readingVelocityPagesPerHour: 30,
        ),
      );

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) async => Ok([
        ReadingHistoryItem(
          sessionId: 1,
          seriesId: 1,
          seriesTitle: 'Solo Leveling',
          chapterId: 10,
          chapterTitle: 'Chapter 10',
          startPage: 1,
          endPage: 12,
          pagesRead: 12,
          startedAt: DateTime(2024, 6),
        ),
      ]);

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) async =>
      const Ok([
        ReadingCalendarDay(day: '2024-06-01', sessions: 1, pagesRead: 12, hasActivity: true),
      ]);

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
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> search(String query, {int page = 1}) =>
      throw UnimplementedError();

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
  Future<Result<List<Collection>>> listCollections() => throw UnimplementedError();

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) =>
      throw UnimplementedError();

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
  Future<Result<void>> toggleFavorite(int seriesId) async => const Ok(null);

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async => const Ok([]);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);
}

class _FakeUpdatesRepository implements UpdatesRepository {
  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async =>
      Ok([
        UpdateNotification(
          id: 1,
          trackerId: 1,
          source: 'test',
          seriesId: 'solo',
          seriesTitle: 'Solo Leveling',
          chapterId: 'ch-1',
          chapterTitle: 'Chapter 1',
          isRead: false,
          createdAt: DateTime(2024, 6),
        ),
      ]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(1);

  @override
  Future<Result<void>> markRead(int notificationId) async => const Ok(null);

  @override
  Future<Result<void>> markAllRead() async => const Ok(null);

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async => const Ok([
        SeriesTracker(
          id: 1,
          source: 'test',
          seriesId: 'solo',
          seriesTitle: 'Solo Leveling',
          trackKind: TrackKind.followed,
          enabled: true,
          notify: true,
          autoDownload: false,
          knownChapterCount: 10,
        ),
      ]);

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async =>
      const Ok(null);

  @override
  Future<Result<void>> deleteTracker(int trackerId) async => const Ok(null);

  @override
  Future<Result<void>> updateTracker(
    int trackerId, {
    bool? autoDownload,
  }) async =>
      const Ok(null);

  @override
  Future<Result<void>> triggerCheck() async => const Ok(null);
}

class _FakeSourcesRepository implements SourcesRepository {
  @override
  Future<Result<List<SourceSummary>>> listSources() async => const Ok([
        SourceSummary(
          id: 'asura',
          name: 'Asura Scans',
          description: 'Test source connector',
          browsable: true,
          supportsImport: true,
        ),
      ]);

  /// The Sources screen renders a pinned section, so this has to answer even
  /// though this test only asserts on the row list.
  @override
  Future<Result<List<SourcePin>>> listPins() async => const Ok([]);

  @override
  Future<Result<List<SourcePin>>> replacePins(List<String> sourceIds) =>
      throw UnimplementedError();

  @override
  Future<Result<GroupedSearchResult>> searchGrouped(
    String query, {
    int page = 1,
    int perPage = 40,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<SourceSeriesSummary>> getSeries(String sourceId, String seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourceChapterSummary>>> getChapters(
    String sourceId,
    String seriesId,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<ReaderChapter>> getReaderChapter(
    String sourceId,
    String seriesId,
    String chapterId,
  ) =>
      throw UnimplementedError();
}

Future<Widget> _wrap(
  Widget child, {
  required List<Override> overrides,
  // The update banner branches on the platform, which the screens read from
  // the theme rather than dart:io so both branches stay reachable here.
  TargetPlatform platform = TargetPlatform.android,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      ...overrides,
    ],
    child: MaterialApp(
      theme: ThemeData(platform: platform),
      home: child,
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Remaining screens', () {
    testWidgets('StatisticsScreen renders stat cards', (tester) async {
      await tester.pumpWidget(
        await _wrap(
          const StatisticsScreen(),
          overrides: [
            libraryRepositoryProvider.overrideWithValue(_FakeIntelligenceRepository()),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      // Title is rendered by HeroHeading, which uppercases its text.
      expect(find.text('READING STATISTICS'), findsWidgets);
      expect(find.text('Total Series'), findsOneWidget);
    });

    testWidgets('RecommendationsScreen renders series card', (tester) async {
      await tester.pumpWidget(
        await _wrap(
          const RecommendationsScreen(),
          overrides: [
            libraryRepositoryProvider.overrideWithValue(_FakeIntelligenceRepository()),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Recommended Title'), findsWidgets);
    });

    testWidgets('ReadingHistoryScreen renders sessions', (tester) async {
      await tester.pumpWidget(
        await _wrap(
          const ReadingHistoryScreen(),
          overrides: [
            libraryRepositoryProvider.overrideWithValue(_FakeIntelligenceRepository()),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Solo Leveling'), findsWidgets);
    });

    testWidgets('UpdatesScreen renders notifications', (tester) async {
      await tester.pumpWidget(
        await _wrap(
          const UpdatesScreen(),
          overrides: [
            updatesRepositoryProvider.overrideWithValue(_FakeUpdatesRepository()),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      // "Check all now" is now a PrimaryPillButton, which uppercases its label.
      expect(find.text('CHECK ALL NOW'), findsOneWidget);
      expect(find.text('Solo Leveling'), findsWidgets);
    });

    testWidgets('SourcesListScreen renders source card', (tester) async {
      await tester.pumpWidget(
        await _wrap(
          const SourcesListScreen(),
          overrides: [
            sourcesRepositoryProvider.overrideWithValue(_FakeSourcesRepository()),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Asura Scans'), findsWidgets);
    });

    testWidgets('SettingsScreen renders tabs', (tester) async {
      await tester.pumpWidget(
        await _wrap(const SettingsScreen(), overrides: [
          appUpdateProvider.overrideWith((ref) async => null),
        ],),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('General'), findsOneWidget);
      expect(find.text('Server'), findsOneWidget);
      expect(find.text('About'), findsOneWidget);
    });

    testWidgets('MoreScreen renders navigation tiles', (tester) async {
      // MoreScreen is a lazy ListView; the "Settings" tile sits below the fold
      // of the default 800x600 surface and isn't built until scrolled into
      // view. Give the test a tall surface so every tile is laid out.
      await tester.binding.setSurfaceSize(const Size(600, 2000));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        await _wrap(
          const MoreScreen(),
          overrides: [
            updatesRepositoryProvider.overrideWithValue(_FakeUpdatesRepository()),
            appUpdateProvider.overrideWith((ref) async => null),
          ],
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Updates'), findsWidgets);
      expect(find.text('Collections'), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('MoreScreen shows update banner when update available',
        (tester) async {
      const updateInfo = AppVersionInfo(
        localVersion: '1.0.0',
        localBuild: 1,
        remoteVersion: '1.1.0',
        remoteBuild: 2,
        downloadUrl: 'http://localhost:8000/app/download',
        channel: AppUpdateChannel.apk,
      );
      final widget = await _wrap(
        const MoreScreen(),
        overrides: [
          updatesRepositoryProvider.overrideWithValue(_FakeUpdatesRepository()),
          appUpdateProvider.overrideWith((ref) async => updateInfo),
        ],
      );
      await tester.pumpWidget(widget);
      // runAsync lets the Dart event loop drain so FutureProvider resolves.
      await tester.runAsync(() async => Future<void>.delayed(Duration.zero));
      await tester.pump();
      await tester.pump();

      expect(find.text('Update available', skipOffstage: false), findsOneWidget);
      expect(find.text('Installed', skipOffstage: false), findsOneWidget);
      expect(find.text('Available', skipOffstage: false), findsOneWidget);
      expect(find.text('v1.0.0', skipOffstage: false), findsOneWidget);
      expect(find.text('v1.1.0', skipOffstage: false), findsOneWidget);
      expect(find.text('(build 1)', skipOffstage: false), findsOneWidget);
      expect(find.text('(build 2)', skipOffstage: false), findsOneWidget);
    });

    testWidgets('MoreScreen never offers an APK download on iOS',
        (tester) async {
      // The banner's whole payload is "Download update" → /app/download, an
      // Android package an iPhone cannot open, plus install instructions that
      // talk about the notification shade. Even handed an APK-channel result
      // that says an update exists, none of it may reach an iPhone.
      const updateInfo = AppVersionInfo(
        localVersion: '1.0.0',
        localBuild: 1,
        remoteVersion: '1.1.0',
        remoteBuild: 2,
        downloadUrl: 'http://localhost:8000/app/download',
        channel: AppUpdateChannel.apk,
      );
      final widget = await _wrap(
        const MoreScreen(),
        platform: TargetPlatform.iOS,
        overrides: [
          updatesRepositoryProvider.overrideWithValue(_FakeUpdatesRepository()),
          appUpdateProvider.overrideWith((ref) async => updateInfo),
        ],
      );
      await tester.pumpWidget(widget);
      await tester.runAsync(() async => Future<void>.delayed(Duration.zero));
      await tester.pump();
      await tester.pump();

      expect(find.text('Update available', skipOffstage: false), findsNothing);
      expect(find.text('Download update', skipOffstage: false), findsNothing);
      // The rest of the tab is untouched.
      expect(find.text('Settings', skipOffstage: false), findsOneWidget);
    });
  });
}