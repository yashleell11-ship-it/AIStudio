import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/library/screens/recommendations_screen.dart';
import 'package:aistudio_mobile/features/library/screens/reading_history_screen.dart';
import 'package:aistudio_mobile/features/library/screens/statistics_screen.dart';
import 'package:aistudio_mobile/features/settings/screens/settings_screen.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository.dart';
import 'package:aistudio_mobile/features/sources/screens/sources_list_screen.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository.dart';
import 'package:aistudio_mobile/features/updates/screens/updates_screen.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

SeriesSummary _series({required int id, required String title}) {
  return SeriesSummary(
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
    createdAt: DateTime(2024, 1, 1),
    updatedAt: DateTime(2024, 6, 1),
  );
}

class _FakeIntelligenceRepository implements LibraryRepository {
  @override
  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20}) async =>
      Ok([_series(id: 1, title: 'Recommended Title')]);

  @override
  Future<Result<LibraryStatistics>> statistics() async => Ok(
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
          startedAt: DateTime(2024, 6, 1),
        ),
      ]);

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) async =>
      Ok([
        ReadingCalendarDay(day: '2024-06-01', sessions: 1, pagesRead: 12, hasActivity: true),
      ]);

  @override
  Future<Result<PagedResult<SeriesSummary>>> listSeries({
    int page = 1,
    int perPage = 20,
    String? sort,
    String? search,
    String? status,
    String? readingStatus,
    int? collectionId,
    int? tagId,
    bool? isFavorite,
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
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
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
          createdAt: DateTime(2024, 6, 1),
        ),
      ]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(1);

  @override
  Future<Result<void>> markRead(int notificationId) async => const Ok(null);

  @override
  Future<Result<void>> markAllRead() async => const Ok(null);

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async => Ok([
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
  Future<Result<void>> triggerCheck() async => const Ok(null);
}

class _FakeSourcesRepository implements SourcesRepository {
  @override
  Future<Result<List<SourceSummary>>> listSources() async => Ok([
        const SourceSummary(
          id: 'asura',
          name: 'Asura Scans',
          description: 'Test source connector',
          browsable: true,
          supportsImport: true,
        ),
      ]);

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

Future<Widget> _wrap(Widget child, {required List<Override> overrides}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    overrides: [
      apiBaseUrlProvider.overrideWithValue('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      ...overrides,
    ],
    child: MaterialApp(home: child),
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
      expect(find.text('Reading Statistics'), findsWidgets);
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
      expect(find.text('Check all now'), findsOneWidget);
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
        await _wrap(const SettingsScreen(), overrides: []),
      );
      expect(find.text('Server'), findsOneWidget);
      expect(find.text('Downloads'), findsOneWidget);
    });
  });
}
