import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/collection.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/recommendation.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/models/tag.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/library_screen.dart';
import 'package:manhwamaniacs/features/library/utils/library_preferences.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../support/test_overrides.dart';

/// `LibraryRepository` double for the Library (followed) browse screen. Only
/// [listSeries] (search/filter/sort all funnel through it — see
/// `fetchLibraryListPage`) and [patchSeries] (favorite toggling) are wired;
/// everything else throws so an unexpected call fails loudly instead of
/// silently returning empty data.
class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository(this._items);

  final List<FollowedSeries> _items;
  String? lastSearch;
  String? lastReadingStatus;
  String? lastSort;
  bool? lastIsFavorite;

  @override
  Future<Result<PagedResult<FollowedSeries>>> listSeries({
    int page = 1,
    int perPage = 40,
    String? sort,
    String? search,
    String? readingStatus,
    bool? isFavorite,
  }) async {
    lastSort = sort;
    lastReadingStatus = readingStatus;
    lastSearch = search;
    lastIsFavorite = isFavorite;

    var items = List<FollowedSeries>.from(_items);
    if (search != null && search.isNotEmpty) {
      items = items
          .where((item) => item.title.toLowerCase().contains(search.toLowerCase()))
          .toList();
    }
    if (readingStatus != null) {
      items = items.where((item) => item.readingStatus == readingStatus).toList();
    }
    if (isFavorite != null) {
      items = items.where((item) => item.isFavorite == isFavorite).toList();
    }
    return Ok(
      PagedResult(
        items: items,
        total: items.length,
        page: 1,
        perPage: perPage,
        hasNext: false,
      ),
    );
  }

  @override
  Future<Result<FollowedSeries>> patchSeries(
    int followedId, {
    bool? isFavorite,
    String? readingStatus,
    bool? notify,
    bool? matureOverride,
    int? sortOrder,
  }) async {
    final current = _items.firstWhere((series) => series.id == followedId);
    return Ok(current.copyWith(isFavorite: isFavorite, readingStatus: readingStatus));
  }

  @override
  Future<Result<SeriesDetail>> getSeries(int followedId) => throw UnimplementedError();

  @override
  Future<Result<FollowedSeries>> follow({
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> unfollow(int followedId) => throw UnimplementedError();

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 10}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<FollowedSeries>>> recentlyUpdated({int limit = 10}) =>
      throw UnimplementedError();

  @override
  Future<Result<List<RecommendationGenre>>> recommendations({int limit = 10}) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<FollowedSeries>>> search(
    String query, {
    int page = 1,
    int perPage = 20,
  }) =>
      throw UnimplementedError('search should not be called');

  @override
  Future<Result<LibraryStatistics>> statistics() => throw UnimplementedError();

  @override
  Future<Result<List<ReadingHistoryItem>>> readingHistory({
    int limit = 50,
    int offset = 0,
  }) =>
      throw UnimplementedError();

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
    int? sortOrder,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteCollection(int collectionId) => throw UnimplementedError();

  @override
  Future<Result<CollectionDetail>> addSeriesToCollection(
    int collectionId, {
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeSeriesFromCollection(
    int collectionId, {
    required String sourceId,
    required String seriesKey,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags({String? category}) => throw UnimplementedError();

  @override
  Future<Result<Tag>> createTag({
    required String name,
    String category = 'custom',
    String? color,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> deleteTag(int tagId) => throw UnimplementedError();

  @override
  Future<Result<void>> addTagToSeries({
    required String sourceId,
    required String seriesKey,
    required int tagId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> removeTagFromSeries({
    required String sourceId,
    required String seriesKey,
    required int tagId,
  }) =>
      throw UnimplementedError();
}

FollowedSeries _series({
  required int id,
  required String title,
  String seriesKey = 'series',
  bool isFavorite = false,
  String readingStatus = 'reading',
  int chapterCount = 10,
  DateTime? createdAt,
  DateTime? updatedAt,
}) {
  return FollowedSeries(
    id: id,
    sourceId: 'asurascans',
    seriesKey: seriesKey,
    title: title,
    coverUrl: '',
    isFavorite: isFavorite,
    readingStatus: readingStatus,
    notify: false,
    sortOrder: 0,
    contentRating: 'safe',
    rating: 'safe',
    chapterCount: chapterCount,
    createdAt: createdAt ?? DateTime(2024),
    updatedAt: updatedAt ?? DateTime(2024, 6),
  );
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
              _series(
                id: 1,
                title: 'Solo Leveling',
                seriesKey: 'solo-leveling',
                isFavorite: true,
                chapterCount: 179,
                createdAt: DateTime(2024),
                updatedAt: DateTime(2024, 6),
              ),
              _series(
                id: 2,
                title: 'Tower of God',
                seriesKey: 'tower-of-god',
                readingStatus: 'completed',
                chapterCount: 120,
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
        _series(
          id: 1,
          title: 'Solo Leveling',
          seriesKey: 'solo-leveling',
        ),
        _series(
          id: 2,
          title: 'Tower of God',
          seriesKey: 'tower-of-god',
          readingStatus: 'completed',
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
        _series(
          id: 2,
          title: 'Tower of God',
          seriesKey: 'tower-of-god',
          readingStatus: 'completed',
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

      expect(readLibraryQuery(prefs).sort, LibrarySort.recentlyAdded);
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

      // Normal AppBar shows the HeroHeading title, which uppercases to "LIBRARY".
      expect(find.text('LIBRARY'), findsOneWidget);
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
      // Normal AppBar shows the HeroHeading title, which uppercases to "LIBRARY".
      expect(find.text('LIBRARY'), findsOneWidget);
      expect(find.byIcon(Icons.checklist), findsOneWidget);
    });
  });
}
