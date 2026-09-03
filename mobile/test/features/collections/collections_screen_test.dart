import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/collections/screens/collections_screen.dart';
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

Collection _sampleCollection({required int id, required String name}) {
  return Collection(
    id: id,
    name: name,
    description: 'Curated picks',
    seriesCount: 2,
    sortOrder: id,
    createdAt: DateTime(2024),
    updatedAt: DateTime(2024, 6),
  );
}

class _FakeCollectionsRepository implements LibraryRepository {
  _FakeCollectionsRepository({List<Collection>? collections})
      : collections = collections ?? [];

  final List<Collection> collections;

  @override
  Future<Result<List<Collection>>> listCollections() async => Ok(collections);

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<Collection>> createCollection({
    required String name,
    String? description,
  }) async {
    final created = _sampleCollection(id: collections.length + 1, name: name);
    collections.add(created);
    return Ok(created);
  }

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
  Future<Result<List<FollowedSeries>>> recommendations({int limit = 20}) =>
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

class _FailingCollectionsRepository extends _FakeCollectionsRepository {
  @override
  Future<Result<List<Collection>>> listCollections() async =>
      const Err(UnknownError(message: 'network failure'));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CollectionsScreen', () {
    testWidgets('renders collection banners and search toolbar', (tester) async {
      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            libraryRepositoryProvider.overrideWithValue(
              _FakeCollectionsRepository(
                collections: [
                  _sampleCollection(id: 1, name: 'Action Picks'),
                  _sampleCollection(id: 2, name: 'Slow Burn'),
                ],
              ),
            ),
          ],
          child: const MaterialApp(home: CollectionsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Action Picks'), findsWidgets);
      expect(find.text('Slow Burn'), findsWidgets);
      expect(find.text('2 collections'), findsOneWidget);
      expect(find.byType(TextField), findsOneWidget);
    });

    testWidgets('shows empty state when no collections exist', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            libraryRepositoryProvider.overrideWithValue(_FakeCollectionsRepository()),
          ],
          child: const MaterialApp(home: CollectionsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('No collections yet'), findsOneWidget);
      expect(find.text('Create your first collection'), findsOneWidget);
    });

    testWidgets('shows retry on load failure', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            libraryRepositoryProvider.overrideWithValue(_FailingCollectionsRepository()),
          ],
          child: const MaterialApp(home: CollectionsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Retry'), findsOneWidget);
    });

    testWidgets('creates a collection from the dialog', (tester) async {
      final repo = _FakeCollectionsRepository();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [libraryRepositoryProvider.overrideWithValue(repo)],
          child: const MaterialApp(home: CollectionsScreen()),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byTooltip('New Collection'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'Must Read');
      await tester.pump();
      await tester.tap(find.widgetWithText(FilledButton, 'Create'));
      await tester.pumpAndSettle();

      expect(find.text('Must Read'), findsWidgets);
      expect(find.text('1 collection'), findsOneWidget);
    });
  });
}