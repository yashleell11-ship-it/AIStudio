import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/collections/providers/collections_provider.dart';
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
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

class _CollectionsRepo implements LibraryRepository {
  _CollectionsRepo(this.items);

  final List<Collection> items;

  @override
  Future<Result<List<Collection>>> listCollections() async => Ok(items);

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) async {
    final created = Collection(
      id: items.length + 1,
      name: name,
      description: description,
      seriesCount: 0,
      sortOrder: items.length + 1,
      createdAt: DateTime(2024),
      updatedAt: DateTime(2024, 6),
    );
    items.add(created);
    return Ok(created);
  }

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) =>
      throw UnimplementedError();

  @override
  Future<Result<Collection>> updateCollection(
    int collectionId, {
    String? name,
    String? description,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteCollection(int collectionId) async {
    items.removeWhere((item) => item.id == collectionId);
    return const Ok(null);
  }

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeSeriesFromCollection(int collectionId, int seriesId) =>
      throw UnimplementedError();

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
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags() => throw UnimplementedError();

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
  Future<Result<List<FollowedSeries>>> recommendations({int limit = 20}) =>
      throw UnimplementedError();

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> search(String query, {int page = 1}) =>
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

void main() {
  group('CollectionsNotifier', () {
    test('createCollection refreshes list', () async {
      final repo = _CollectionsRepo([]);
      final container = ProviderContainer(
        overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(collectionsProvider.future);
      expect(container.read(collectionsProvider).value, isEmpty);

      final error = await container.read(collectionsProvider.notifier).createCollection(
            name: 'Must Read',
            description: 'Top picks',
          );

      expect(error, isNull);
      final collections = container.read(collectionsProvider).value!;
      expect(collections, hasLength(1));
      expect(collections.first.name, 'Must Read');
    });

    test('deleteCollection removes item via repository', () async {
      final repo = _CollectionsRepo([
        Collection(
          id: 1,
          name: 'Action Picks',
          seriesCount: 0,
          sortOrder: 1,
          createdAt: DateTime(2024),
          updatedAt: DateTime(2024, 6),
        ),
      ]);
      final container = ProviderContainer(
        overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
      );
      addTearDown(container.dispose);

      await container.read(collectionsProvider.future);
      await repo.deleteCollection(1);
      await container.read(collectionsProvider.notifier).refresh();

      expect(container.read(collectionsProvider).value, isEmpty);
    });
  });
}