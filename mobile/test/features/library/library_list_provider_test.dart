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
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/providers/library_list_provider.dart';
import 'package:aistudio_mobile/features/library/utils/library_preferences.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository(this.pages);

  final Map<int, PagedResult<SeriesSummary>> pages;
  int listCalls = 0;
  String? lastReadingStatus;
  String? lastSort;
  bool? lastHasChapters;

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
  }) async {
    listCalls++;
    lastReadingStatus = readingStatus;
    lastSort = sort;
    lastHasChapters = hasChapters;
    return Ok(pages[page] ?? pages[1]!);
  }

  @override
  Future<Result<void>> toggleFavorite(int seriesId) async => const Ok(null);

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

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
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) =>
      throw UnimplementedError();

  @override
  Future<Result<SeriesDetail>> getSeries(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({int limit = 50}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<ReadingCalendarDay>>> readingCalendar({int days = 30}) =>
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

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

SeriesSummary _series(int id) {
  return SeriesSummary(
    id: id,
    libraryId: 1,
    title: 'Series $id',
    sortTitle: 'series $id',
    contentRating: 'teen',
    language: 'en',
    folderPath: '/library/$id',
    isFavorite: false,
    readingStatus: 'unread',
    chapterCount: 10,
    readChapters: 0,
    pageCount: 100,
    totalChapters: 10,
    totalPages: 100,
    createdAt: DateTime(2024, 1, 1),
    updatedAt: DateTime(2024, 6, 1),
  );
}

void main() {
  group('LibraryListNotifier', () {
    Future<ProviderContainer> _container(_FakeLibraryRepository fakeRepo) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final container = ProviderContainer(
        overrides: [
          libraryRepositoryProvider.overrideWithValue(fakeRepo),
          sharedPrefsProvider.overrideWithValue(prefs),
        ],
      );
      addTearDown(container.dispose);
      return container;
    }

    test('loads first page and appends on loadMore', () async {
      final fakeRepo = _FakeLibraryRepository({
        1: PagedResult(
          items: [_series(1), _series(2)],
          total: 4,
          page: 1,
          perPage: 2,
          hasNext: true,
        ),
        2: PagedResult(
          items: [_series(3), _series(4)],
          total: 4,
          page: 2,
          perPage: 2,
          hasNext: false,
        ),
      });

      final container = await _container(fakeRepo);

      final state = await container.read(libraryListProvider.future);
      expect(state.items, hasLength(2));
      expect(state.hasNext, isTrue);

      await container.read(libraryListProvider.notifier).loadMore();
      final loaded = container.read(libraryListProvider).value!;
      expect(loaded.items, hasLength(4));
      expect(loaded.hasNext, isFalse);
      expect(fakeRepo.listCalls, 2);
    });

    test('passes reading status filter to repository', () async {
      final fakeRepo = _FakeLibraryRepository({
        1: PagedResult(
          items: [_series(1)],
          total: 1,
          page: 1,
          perPage: 20,
          hasNext: false,
        ),
      });

      final container = await _container(fakeRepo);

      container.read(libraryQueryProvider.notifier).updateQuery(
            const LibraryQuery(
              filter: LibraryFilter.completed,
              sort: LibrarySort.recent,
            ),
          );
      await container.read(libraryListProvider.future);

      expect(fakeRepo.lastReadingStatus, 'completed');
      expect(fakeRepo.lastSort, 'recent');
    });

    test('downloaded filter passes has_chapters and preserves pagination', () async {
      final fakeRepo = _FakeLibraryRepository({
        1: PagedResult(
          items: [_series(1), _series(2)],
          total: 3,
          page: 1,
          perPage: 2,
          hasNext: true,
        ),
        2: PagedResult(
          items: [_series(3)],
          total: 3,
          page: 2,
          perPage: 2,
          hasNext: false,
        ),
      });

      final container = await _container(fakeRepo);

      container.read(libraryQueryProvider.notifier).updateQuery(
            const LibraryQuery(filter: LibraryFilter.downloaded),
          );
      final state = await container.read(libraryListProvider.future);

      expect(fakeRepo.lastHasChapters, isTrue);
      expect(state.total, 3);
      expect(state.items, hasLength(2));
      expect(state.hasNext, isTrue);

      await container.read(libraryListProvider.notifier).loadMore();
      final loaded = container.read(libraryListProvider).value!;

      expect(loaded.items, hasLength(3));
      expect(loaded.total, 3);
      expect(loaded.hasNext, isFalse);
      expect(fakeRepo.listCalls, 2);
    });

    test('search-only query update does not write preferences', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      await writeLibraryQuery(prefs, const LibraryQuery());
      final before = prefs.getString(libraryQueryPrefsKey);

      final container = ProviderContainer(
        overrides: [
          libraryRepositoryProvider.overrideWithValue(_FakeLibraryRepository({
            1: PagedResult(
              items: [_series(1)],
              total: 1,
              page: 1,
              perPage: 20,
              hasNext: false,
            ),
          })),
          sharedPrefsProvider.overrideWithValue(prefs),
        ],
      );
      addTearDown(container.dispose);

      container.read(libraryQueryProvider.notifier).patchQuery(
            (query) => query.copyWith(search: 'solo'),
          );

      expect(prefs.getString(libraryQueryPrefsKey), equals(before));
      expect(container.read(libraryQueryProvider).search, 'solo');
    });

    test('persisted query fields still write preferences', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      await writeLibraryQuery(prefs, const LibraryQuery());

      final container = ProviderContainer(
        overrides: [
          libraryRepositoryProvider.overrideWithValue(_FakeLibraryRepository({
            1: PagedResult(
              items: [_series(1)],
              total: 1,
              page: 1,
              perPage: 20,
              hasNext: false,
            ),
          })),
          sharedPrefsProvider.overrideWithValue(prefs),
        ],
      );
      addTearDown(container.dispose);

      container.read(libraryQueryProvider.notifier).patchQuery(
            (query) => query.copyWith(sort: LibrarySort.dateAdded),
          );

      expect(readLibraryQuery(prefs).sort, LibrarySort.dateAdded);
    });

    test('applyLibraryClientFilters skips downloaded filter for browse', () {
      final items = [
        _series(1),
        SeriesSummary(
          id: 2,
          libraryId: 1,
          title: 'Empty',
          sortTitle: 'empty',
          contentRating: 'teen',
          language: 'en',
          folderPath: '/library/2',
          isFavorite: false,
          readingStatus: 'unread',
          chapterCount: 0,
          readChapters: 0,
          pageCount: 0,
          totalChapters: 0,
          totalPages: 0,
          createdAt: DateTime(2024, 1, 1),
          updatedAt: DateTime(2024, 6, 1),
        ),
      ];

      final filtered = applyLibraryClientFilters(
        items,
        const LibraryQuery(filter: LibraryFilter.downloaded),
        sortResults: false,
      );

      expect(filtered, hasLength(2));
    });

    test('applyLibraryClientFilters keeps downloaded filter for search', () {
      final items = [
        _series(1),
        SeriesSummary(
          id: 2,
          libraryId: 1,
          title: 'Empty',
          sortTitle: 'empty',
          contentRating: 'teen',
          language: 'en',
          folderPath: '/library/2',
          isFavorite: false,
          readingStatus: 'unread',
          chapterCount: 0,
          readChapters: 0,
          pageCount: 0,
          totalChapters: 0,
          totalPages: 0,
          createdAt: DateTime(2024, 1, 1),
          updatedAt: DateTime(2024, 6, 1),
        ),
      ];

      final filtered = applyLibraryClientFilters(
        items,
        const LibraryQuery(filter: LibraryFilter.downloaded, search: 'solo'),
        sortResults: false,
      );

      expect(filtered, hasLength(1));
      expect(filtered.first.id, 1);
    });
  });
}
