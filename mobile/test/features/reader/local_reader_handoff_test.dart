import 'package:aistudio_mobile/core/utils/result.dart';
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
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/features/reader/utils/local_reader_handoff.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

class _ChapterLookupRepository implements LibraryRepository {
  _ChapterLookupRepository(this.chapter);

  final ChapterDetail chapter;

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) async => Ok(chapter);

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
    bool? hasChapters,
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

DownloadItem _completedDownload({int? localChapterId}) => DownloadItem(
      id: 1,
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
      localChapterId: localChapterId,
      createdAt: DateTime.utc(2024, 1, 1),
      updatedAt: DateTime.utc(2024, 1, 1),
      priority: 0,
      retryCount: 0,
    );

void main() {
  group('libraryReaderPath', () {
    test('builds library reader route', () {
      expect(
        libraryReaderPath(5, 42),
        '/library/5/chapters/42/read',
      );
    });

    test('includes page query when initial page is greater than one', () {
      expect(
        libraryReaderPath(5, 42, initialPage: 3),
        '/library/5/chapters/42/read?page=3',
      );
    });
  });

  group('openDownloadedChapter', () {
    testWidgets('navigates to library reader using local chapter id', (tester) async {
      final chapter = ChapterDetail(
        id: 42,
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
      );
      final repo = _ChapterLookupRepository(chapter);
      String? navigatedLocation;

      final router = GoRouter(
        initialLocation: '/downloads',
        routes: [
          GoRoute(
            path: '/downloads',
            builder: (_, __) => Consumer(
              builder: (context, ref, _) => Scaffold(
                body: FilledButton(
                  onPressed: () => openDownloadedChapter(
                    context,
                    ref,
                    _completedDownload(localChapterId: 42),
                  ),
                  child: const Text('Open'),
                ),
              ),
            ),
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

      await tester.pumpWidget(
        ProviderScope(
          overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.tap(find.text('Open'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(navigatedLocation, '/library/7/chapters/42/read');
      expect(find.text('LIBRARY READER'), findsOneWidget);
    });

    testWidgets('shows snackbar when local chapter id is missing', (tester) async {
      final router = GoRouter(
        routes: [
          GoRoute(
            path: '/',
            builder: (_, __) => Consumer(
              builder: (context, ref, _) => Scaffold(
                body: FilledButton(
                  onPressed: () => openDownloadedChapter(
                    context,
                    ref,
                    _completedDownload(),
                  ),
                  child: const Text('Open'),
                ),
              ),
            ),
          ),
        ],
      );

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.tap(find.text('Open'));
      await tester.pump();

      expect(find.text('This download is not available offline yet.'), findsOneWidget);
    });
  });
}
