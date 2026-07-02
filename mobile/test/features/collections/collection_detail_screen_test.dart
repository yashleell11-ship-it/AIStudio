import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/collections/providers/collection_detail_provider.dart';
import 'package:aistudio_mobile/features/collections/providers/collections_provider.dart';
import 'package:aistudio_mobile/features/collections/screens/collection_detail_screen.dart';
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
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

SeriesSummary _series(int id, String title) => SeriesSummary(
      id: id,
      libraryId: 1,
      title: title,
      sortTitle: title.toLowerCase(),
      contentRating: 'teen',
      language: 'en',
      folderPath: '/library/$id',
      isFavorite: false,
      readingStatus: 'reading',
      chapterCount: 10,
      readChapters: 1,
      pageCount: 100,
      totalChapters: 10,
      totalPages: 100,
      createdAt: DateTime(2024, 1, 1),
      updatedAt: DateTime(2024, 6, 1),
    );

class _MutableCollectionsRepository implements LibraryRepository {
  _MutableCollectionsRepository({
    required this.collections,
    required Map<int, CollectionDetail> details,
    List<SeriesSummary>? pickerSeries,
  })  : _details = details,
        _pickerSeries = pickerSeries ?? [_series(1, 'Solo Leveling'), _series(2, 'Tower of God')];

  final List<Collection> collections;
  final Map<int, CollectionDetail> _details;
  List<SeriesSummary> _pickerSeries;

  int renameCalls = 0;
  int deleteCalls = 0;
  int addSeriesCalls = 0;
  int removeSeriesCalls = 0;

  @override
  Future<Result<List<Collection>>> listCollections() async => Ok(collections);

  @override
  Future<Result<CollectionDetail>> getCollection(int collectionId) async {
    final detail = _details[collectionId];
    if (detail == null) {
      return Err(UnknownError(message: 'missing collection'));
    }
    return Ok(detail);
  }

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
  }) async {
    renameCalls++;
    final detail = _details[collectionId]!;
    final updated = CollectionDetail(
      id: detail.id,
      name: name ?? detail.name,
      description: description ?? detail.description,
      coverPath: detail.coverPath,
      seriesCount: detail.series.total,
      sortOrder: detail.sortOrder,
      createdAt: detail.createdAt,
      updatedAt: DateTime(2024, 7, 2),
      series: detail.series,
    );
    _details[collectionId] = updated;
    return Ok(
      Collection(
        id: updated.id,
        name: updated.name,
        description: updated.description,
        coverPath: updated.coverPath,
        seriesCount: updated.series.total,
        sortOrder: updated.sortOrder,
        createdAt: updated.createdAt,
        updatedAt: updated.updatedAt,
      ),
    );
  }

  @override
  Future<Result<void>> deleteCollection(int collectionId) async {
    deleteCalls++;
    collections.removeWhere((item) => item.id == collectionId);
    _details.remove(collectionId);
    return const Ok(null);
  }

  @override
  Future<Result<void>> addSeriesToCollection(int collectionId, int seriesId) async {
    addSeriesCalls++;
    final detail = _details[collectionId]!;
    final series = _pickerSeries.firstWhere((item) => item.id == seriesId);
    _details[collectionId] = CollectionDetail(
      id: detail.id,
      name: detail.name,
      description: detail.description,
      coverPath: detail.coverPath,
      seriesCount: detail.series.items.length + 1,
      sortOrder: detail.sortOrder,
      createdAt: detail.createdAt,
      updatedAt: detail.updatedAt,
      series: PagedResult(
        items: [...detail.series.items, series],
        total: detail.series.items.length + 1,
        page: 1,
        perPage: 200,
        hasNext: false,
      ),
    );
    return const Ok(null);
  }

  @override
  Future<Result<void>> removeSeriesFromCollection(
    int collectionId,
    int seriesId,
  ) async {
    removeSeriesCalls++;
    final detail = _details[collectionId]!;
    final items =
        detail.series.items.where((item) => item.id != seriesId).toList();
    _details[collectionId] = CollectionDetail(
      id: detail.id,
      name: detail.name,
      description: detail.description,
      coverPath: detail.coverPath,
      seriesCount: items.length,
      sortOrder: detail.sortOrder,
      createdAt: detail.createdAt,
      updatedAt: detail.updatedAt,
      series: PagedResult(
        items: items,
        total: items.length,
        page: 1,
        perPage: 200,
        hasNext: false,
      ),
    );
    return const Ok(null);
  }

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
  }) async =>
      Ok(
        PagedResult(
          items: _pickerSeries,
          total: _pickerSeries.length,
          page: 1,
          perPage: 200,
          hasNext: false,
        ),
      );

  @override
  Future<Result<void>> toggleFavorite(int seriesId) async => const Ok(null);

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

CollectionDetail _detail({
  required int id,
  required String name,
  List<SeriesSummary> series = const [],
}) =>
    CollectionDetail(
      id: id,
      name: name,
      description: 'Curated picks',
      coverPath: null,
      seriesCount: series.length,
      sortOrder: 0,
      createdAt: DateTime(2024, 1, 1),
      updatedAt: DateTime(2024, 6, 1),
      series: PagedResult(
        items: series,
        total: series.length,
        page: 1,
        perPage: 200,
        hasNext: false,
      ),
    );

Future<void> _pumpDetail(
  WidgetTester tester,
  _MutableCollectionsRepository repo,
  int collectionId,
) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        apiBaseUrlProvider.overrideWithValue('http://127.0.0.1:8000'),
        libraryRepositoryProvider.overrideWithValue(repo),
      ],
      child: MaterialApp(
        home: CollectionDetailScreen(collectionId: collectionId),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('CollectionDetailScreen', () {
    testWidgets('shows empty collection state', (tester) async {
      final repo = _MutableCollectionsRepository(
        collections: [
          Collection(
            id: 1,
            name: 'Action Picks',
            description: 'Curated picks',
            coverPath: null,
            seriesCount: 0,
            sortOrder: 0,
            createdAt: DateTime(2024, 1, 1),
            updatedAt: DateTime(2024, 6, 1),
          ),
        ],
        details: {1: _detail(id: 1, name: 'Action Picks')},
      );

      await _pumpDetail(tester, repo, 1);

      expect(find.text('This collection is empty'), findsOneWidget);
      expect(find.text('Add series'), findsOneWidget);
    });

    testWidgets('rename collection updates detail', (tester) async {
      final repo = _MutableCollectionsRepository(
        collections: [
          Collection(
            id: 1,
            name: 'Action Picks',
            description: 'Curated picks',
            coverPath: null,
            seriesCount: 1,
            sortOrder: 0,
            createdAt: DateTime(2024, 1, 1),
            updatedAt: DateTime(2024, 6, 1),
          ),
        ],
        details: {
          1: _detail(
            id: 1,
            name: 'Action Picks',
            series: [_series(1, 'Solo Leveling')],
          ),
        },
      );

      await _pumpDetail(tester, repo, 1);
      expect(find.text('Action Picks'), findsWidgets);

      await tester.tap(find.text('Rename'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField).first, 'Peak Fiction');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();

      expect(repo.renameCalls, 1);
      expect(find.text('Peak Fiction'), findsWidgets);
    });

    testWidgets('add series from dialog updates collection', (tester) async {
      final repo = _MutableCollectionsRepository(
        collections: [
          Collection(
            id: 1,
            name: 'Action Picks',
            description: null,
            coverPath: null,
            seriesCount: 0,
            sortOrder: 0,
            createdAt: DateTime(2024, 1, 1),
            updatedAt: DateTime(2024, 6, 1),
          ),
        ],
        details: {1: _detail(id: 1, name: 'Action Picks')},
      );

      await _pumpDetail(tester, repo, 1);
      await tester.tap(find.text('Add Series').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tower of God'));
      await tester.pumpAndSettle();

      expect(repo.addSeriesCalls, 1);
      expect(find.text('Tower of God'), findsWidgets);
    });

    testWidgets('remove series updates collection', (tester) async {
      final repo = _MutableCollectionsRepository(
        collections: [
          Collection(
            id: 1,
            name: 'Action Picks',
            description: null,
            coverPath: null,
            seriesCount: 1,
            sortOrder: 0,
            createdAt: DateTime(2024, 1, 1),
            updatedAt: DateTime(2024, 6, 1),
          ),
        ],
        details: {
          1: _detail(
            id: 1,
            name: 'Action Picks',
            series: [_series(1, 'Solo Leveling')],
          ),
        },
      );

      await _pumpDetail(tester, repo, 1);
      await tester.tap(find.byIcon(Icons.remove_circle_outline));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Remove'));
      await tester.pumpAndSettle();

      expect(repo.removeSeriesCalls, 1);
      expect(find.text('This collection is empty'), findsOneWidget);
    });
  });
}
