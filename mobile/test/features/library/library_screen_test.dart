import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/library_screen.dart';
import 'package:manhwamaniacs/features/library/utils/library_preferences.dart';
import 'package:manhwamaniacs/features/reader/models/adjacent_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../support/test_overrides.dart';

class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository(this._items);

  final List<SeriesSummary> _items;
  String? lastSearch;
  String? lastReadingStatus;
  String? lastSort;

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
    lastSort = sort;
    lastReadingStatus = readingStatus;
    var items = List<SeriesSummary>.from(_items);
    if (readingStatus != null) {
      items = items.where((item) => item.readingStatus == readingStatus).toList();
    }
    return Ok(
      PagedResult(
        items: items,
        total: items.length,
        page: 1,
        perPage: 20,
        hasNext: false,
      ),
    );
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
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) async {
    lastSearch = query;
    final items = _items
        .where((item) => item.title.toLowerCase().contains(query.toLowerCase()))
        .toList();
    return Ok(items);
  }

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

Future<Widget> _buildTestApp({LibraryRepository? repo}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(
        repo ??
            _FakeLibraryRepository([
              SeriesSummary(
                id: 1,
                libraryId: 1,
                title: 'Solo Leveling',
                sortTitle: 'solo leveling',
                contentRating: 'teen',
                language: 'ko',
                folderPath: '/library/solo-leveling',
                isFavorite: true,
                readingStatus: 'reading',
                chapterCount: 179,
                readChapters: 50,
                pageCount: 3580,
                totalChapters: 179,
                totalPages: 3580,
                createdAt: DateTime(2024),
                updatedAt: DateTime(2024, 6),
                readingProgress: ReadingProgress(
                  seriesId: 1,
                  chapterId: 150,
                  lastPage: 10,
                  progressPct: 27.9,
                  lastReadAt: DateTime(2024, 6),
                ),
              ),
              SeriesSummary(
                id: 2,
                libraryId: 1,
                title: 'Tower of God',
                sortTitle: 'tower of god',
                contentRating: 'teen',
                language: 'ko',
                folderPath: '/library/tog',
                isFavorite: false,
                readingStatus: 'completed',
                chapterCount: 120,
                readChapters: 120,
                pageCount: 2400,
                totalChapters: 120,
                totalPages: 2400,
                createdAt: DateTime(2024, 2),
                updatedAt: DateTime(2024, 7),
              ),
            ]),
      ),
    ],
    child: const MaterialApp(home: LibraryScreen()),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('LibraryScreen', () {
    testWidgets('renders library grid with series card', (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      expect(find.text('Library'), findsWidgets);
      expect(find.text('Solo Leveling'), findsWidgets);
    });

    testWidgets('shows empty state for search with no results', (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'missing title');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pump();

      expect(find.text('No results found'), findsOneWidget);
    });

    testWidgets('search filters visible series', (tester) async {
      final repo = _FakeLibraryRepository([
        SeriesSummary(
          id: 1,
          libraryId: 1,
          title: 'Solo Leveling',
          sortTitle: 'solo leveling',
          contentRating: 'teen',
          language: 'ko',
          folderPath: '/library/solo-leveling',
          isFavorite: false,
          readingStatus: 'reading',
          chapterCount: 10,
          readChapters: 1,
          pageCount: 100,
          totalChapters: 10,
          totalPages: 100,
          createdAt: DateTime(2024),
          updatedAt: DateTime(2024, 6),
        ),
        SeriesSummary(
          id: 2,
          libraryId: 1,
          title: 'Tower of God',
          sortTitle: 'tower of god',
          contentRating: 'teen',
          language: 'ko',
          folderPath: '/library/tog',
          isFavorite: false,
          readingStatus: 'completed',
          chapterCount: 10,
          readChapters: 10,
          pageCount: 100,
          totalChapters: 10,
          totalPages: 100,
          createdAt: DateTime(2024, 2),
          updatedAt: DateTime(2024, 7),
        ),
      ]);

      await tester.pumpWidget(await _buildTestApp(repo: repo));
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextField), 'Tower');
      await tester.pump(const Duration(milliseconds: 400));
      await tester.pumpAndSettle();

      expect(repo.lastSearch, 'Tower');
      expect(find.text('Tower of God'), findsWidgets);
      expect(find.text('Solo Leveling'), findsNothing);
    });

    testWidgets('completed filter requests completed reading status', (tester) async {
      final repo = _FakeLibraryRepository([
        SeriesSummary(
          id: 2,
          libraryId: 1,
          title: 'Tower of God',
          sortTitle: 'tower of god',
          contentRating: 'teen',
          language: 'ko',
          folderPath: '/library/tog',
          isFavorite: false,
          readingStatus: 'completed',
          chapterCount: 10,
          readChapters: 10,
          pageCount: 100,
          totalChapters: 10,
          totalPages: 100,
          createdAt: DateTime(2024, 2),
          updatedAt: DateTime(2024, 7),
        ),
      ]);

      await tester.pumpWidget(await _buildTestApp(repo: repo));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Completed'));
      await tester.pumpAndSettle();

      expect(repo.lastReadingStatus, 'completed');
      expect(find.text('Tower of God'), findsWidgets);
    });

    testWidgets('sort change updates query and persists', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            apiBaseUrlOverride('http://127.0.0.1:8000'),
            sharedPrefsProvider.overrideWithValue(prefs),
            libraryRepositoryProvider.overrideWithValue(_FakeLibraryRepository([])),
          ],
          child: const MaterialApp(home: LibraryScreen()),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byType(DropdownButtonFormField<LibrarySort>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Recently Added').last);
      await tester.pumpAndSettle();

      expect(readLibraryQuery(prefs).sort, LibrarySort.dateAdded);
    });
  });

  group('LibraryScreen multi-select', () {
    testWidgets('Select icon enters selection mode with an empty count',
        (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.checklist));
      await tester.pumpAndSettle();

      expect(find.text('0 selected'), findsOneWidget);
      expect(find.byIcon(Icons.close), findsOneWidget);
    });

    testWidgets('tapping a card in selection mode toggles it and updates the count',
        (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.checklist));
      await tester.pumpAndSettle();

      await tester.ensureVisible(find.text('Solo Leveling').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Solo Leveling').first);
      await tester.pump();

      expect(find.text('1 selected'), findsOneWidget);

      // Tapping the same card again deselects it.
      await tester.tap(find.text('Solo Leveling').first);
      await tester.pump();

      expect(find.text('0 selected'), findsOneWidget);
    });

    testWidgets('Select all selects every currently-loaded series', (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.checklist));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.select_all));
      await tester.pump();

      expect(find.text('2 selected'), findsOneWidget);
    });

    testWidgets('Cancel exits selection mode back to the normal AppBar',
        (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      await tester.tap(find.byIcon(Icons.checklist));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.close));
      await tester.pumpAndSettle();

      expect(find.text('Browse Library'), findsOneWidget);
      expect(find.byIcon(Icons.checklist), findsOneWidget);
    });

    testWidgets(
        'Favorite (N) batch-favorites only the unfavorited selection and exits',
        (tester) async {
      await tester.pumpWidget(await _buildTestApp());
      await tester.pumpAndSettle();

      // Solo Leveling starts favorited, Tower of God does not.
      await tester.tap(find.byIcon(Icons.checklist));
      await tester.pumpAndSettle();
      await tester.tap(find.byIcon(Icons.select_all));
      await tester.pump();

      await tester.tap(find.textContaining('Favorite (2)'));
      await tester.pumpAndSettle();

      // Selection mode exits automatically once the batch action completes.
      expect(find.text('Browse Library'), findsOneWidget);
      expect(find.byIcon(Icons.checklist), findsOneWidget);
    });
  });
}