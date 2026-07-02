import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
import 'package:aistudio_mobile/features/downloads/screens/downloads_screen.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _FakeDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<List<DownloadItem>>> listDownloads() async => Ok([
        DownloadItem(
          id: 1,
          source: 'test',
          seriesId: 'solo',
          chapterId: 'ch-1',
          seriesTitle: 'Solo Leveling',
          chapterTitle: 'Chapter 1',
          status: 'downloading',
          progress: 45,
          pagesDone: 9,
          pagesTotal: 20,
          bytesDownloaded: 4096000,
          speedBps: 512000,
          speedMbps: 0.5,
          etaSeconds: 22,
          createdAt: DateTime.utc(2024, 1, 1),
          updatedAt: DateTime.utc(2024, 1, 1),
          priority: 0,
          retryCount: 0,
        ),
      ]);

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: 1,
          completed: 0,
          failed: 0,
          remaining: 1,
          active: 1,
          queued: 0,
          paused: 0,
          storageUsedBytes: 0,
          storageFreeBytes: 0,
          overallSpeedBps: 512000,
          overallSpeedMbps: 0.5,
          overallEtaSeconds: 22,
          workers: const DownloadWorkers(configured: 2, active: 1, running: 1),
        ),
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> resumeDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> cancelDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<void>> retryDownload(int downloadId) async => const Ok(null);

  @override
  Future<Result<int>> pauseAll() async => const Ok(1);

  @override
  Future<Result<int>> resumeAll() async => const Ok(1);

  @override
  Future<Result<int>> cancelAll() async => const Ok(1);

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) async =>
      const Ok(1);
}

class _CompletedDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<List<DownloadItem>>> listDownloads() async => Ok([
        DownloadItem(
          id: 99,
          source: 'mangadex',
          seriesId: 'manga-1',
          chapterId: 'manga-1:1',
          seriesTitle: 'Solo Leveling',
          chapterTitle: 'Chapter 1',
          status: 'completed',
          progress: 1,
          pagesDone: 10,
          pagesTotal: 10,
          bytesDownloaded: 4096,
          localChapterId: 42,
          createdAt: DateTime.utc(2024, 1, 1),
          updatedAt: DateTime.utc(2024, 1, 1),
          priority: 0,
          retryCount: 0,
        ),
      ]);

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: 1,
          completed: 1,
          failed: 0,
          remaining: 0,
          active: 0,
          queued: 0,
          paused: 0,
          storageUsedBytes: 4096,
          storageFreeBytes: 0,
          overallSpeedBps: 0,
          overallSpeedMbps: 0,
          overallEtaSeconds: null,
          workers: const DownloadWorkers(configured: 2, active: 0, running: 0),
        ),
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> resumeDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> cancelDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> retryDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<int>> pauseAll() => throw UnimplementedError();

  @override
  Future<Result<int>> resumeAll() => throw UnimplementedError();

  @override
  Future<Result<int>> cancelAll() => throw UnimplementedError();

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();
}

class _LibraryChapterLookupRepository implements LibraryRepository {
  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) async => Ok(
        ChapterDetail(
          id: chapterId,
          seriesId: 7,
          title: 'Chapter 1',
          pageCount: 1,
          pages: const [
            PageInfo(
              id: 101,
              chapterId: 42,
              number: 1,
              filePath: '/pages/1.jpg',
            ),
          ],
        ),
      );

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
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recommendations({int limit = 20}) =>
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
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
      throw UnimplementedError();

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async => const Ok([]);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DownloadsScreen', () {
    testWidgets('renders active download queue and metrics', (tester) async {
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            downloadsRepositoryProvider.overrideWithValue(_FakeDownloadsRepository()),
          ],
          child: const MaterialApp(home: DownloadsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Overall Progress'), findsOneWidget);
      expect(find.text('Solo Leveling'), findsWidgets);
      expect(find.text('Pause All'), findsOneWidget);
      expect(find.textContaining('45%'), findsWidgets);
    });

    testWidgets('shows retry on load failure', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            downloadsRepositoryProvider.overrideWithValue(_FailingDownloadsRepository()),
          ],
          child: const MaterialApp(home: DownloadsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('tapping completed download opens library reader', (tester) async {
      String? navigatedLocation;
      final router = GoRouter(
        initialLocation: '/downloads',
        routes: [
          GoRoute(
            path: '/downloads',
            builder: (_, __) => const DownloadsScreen(),
          ),
          GoRoute(
            path: '/library/:seriesId/chapters/:chapterId/read',
            builder: (_, state) {
              navigatedLocation = state.uri.toString();
              return const Scaffold(body: Text('LIBRARY READER'));
            },
          ),
        ],
      );

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            downloadsRepositoryProvider.overrideWithValue(_CompletedDownloadsRepository()),
            libraryRepositoryProvider.overrideWithValue(_LibraryChapterLookupRepository()),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Completed (1)'), findsOneWidget);
      final completedDownloadFinder = find.byKey(const Key('completed-download-99'));
      await tester.ensureVisible(completedDownloadFinder);
      await tester.pumpAndSettle();
      await tester.tap(completedDownloadFinder);
      await tester.pumpAndSettle();
      await tester.pump(const Duration(milliseconds: 100));

      expect(navigatedLocation, '/library/7/chapters/42/read');
      expect(find.text('LIBRARY READER'), findsOneWidget);
    });
  });
}

class _FailingDownloadsRepository implements DownloadsRepository {
  @override
  Future<Result<List<DownloadItem>>> listDownloads() async =>
      Err(UnknownError(message: 'network failure'));

  @override
  Future<Result<DownloadMetrics>> getMetrics() async =>
      Err(UnknownError(message: 'network failure'));

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> resumeDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> cancelDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> retryDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<int>> pauseAll() => throw UnimplementedError();

  @override
  Future<Result<int>> resumeAll() => throw UnimplementedError();

  @override
  Future<Result<int>> cancelAll() => throw UnimplementedError();

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();
}
