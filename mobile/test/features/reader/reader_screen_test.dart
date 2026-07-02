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
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/features/reader/providers/reader_chapter_provider.dart';
import 'package:aistudio_mobile/features/reader/screens/reader_screen.dart';
import '../../support/test_overrides.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeReaderRepository implements LibraryRepository {
  _FakeReaderRepository(this.chapter);

  final ChapterDetail chapter;
  int saveProgressCalls = 0;

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) async => Ok(chapter);

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) async {
    if (direction == 'next') {
      return const Ok(
        AdjacentChapter(id: 2, seriesId: 1, title: 'Chapter 2'),
      );
    }
    return const Ok(null);
  }

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) async {
    saveProgressCalls++;
    return Ok(
      ReadingProgress(
        seriesId: seriesId,
        chapterId: chapterId,
        lastPage: lastPage,
        progressPct: 10,
        lastReadAt: DateTime.utc(2024, 1, 1),
      ),
    );
  }

  @override
  Future<Result<Bookmark>> addBookmark({
    required int seriesId,
    required int chapterId,
    required int page,
    String? note,
  }) async =>
      Ok(
        Bookmark(
          id: 1,
          seriesId: seriesId,
          chapterId: chapterId,
          page: page,
          createdAt: DateTime.utc(2024, 1, 1),
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
  Future<Result<ReadingProgress?>> getProgress(int seriesId) =>
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
  Future<Result<List<Bookmark>>> listBookmarks({int limit = 200}) async => const Ok([]);

  @override
  Future<Result<void>> deleteBookmark(int bookmarkId) async => const Ok(null);
}

ChapterDetail _sampleChapter() {
  return ChapterDetail(
    id: 1,
    seriesId: 1,
    title: 'Chapter 1',
    pageCount: 2,
    pages: const [
      PageInfo(
        id: 101,
        chapterId: 1,
        number: 1,
        filePath: '/pages/1.jpg',
        width: 800,
        height: 1200,
      ),
      PageInfo(
        id: 102,
        chapterId: 1,
        number: 2,
        filePath: '/pages/2.jpg',
        width: 800,
        height: 1200,
      ),
    ],
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('ReaderScreen', () {
    testWidgets('renders chapter controls and page indicator', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final repo = _FakeReaderRepository(_sampleChapter());

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            libraryRepositoryProvider.overrideWithValue(repo),
            apiBaseUrlOverride('http://127.0.0.1:8000'),
          ],
          child: const MaterialApp(
            home: ReaderScreen(seriesId: 1, chapterId: 1, initialPage: 1),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.textContaining('Page 1 / 2'), findsOneWidget);
      expect(find.text('Back'), findsOneWidget);
      expect(find.text('Save'), findsOneWidget);
    });

    testWidgets('shows retry state on chapter load failure', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            readerChapterProvider(1).overrideWith((ref) async {
              throw Exception('network failure');
            }),
          ],
          child: const MaterialApp(
            home: ReaderScreen(seriesId: 1, chapterId: 1),
          ),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Retry'), findsOneWidget);
      expect(find.text('Go back'), findsOneWidget);
    });
  });
}
