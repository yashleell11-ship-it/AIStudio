import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/features/library/screens/library_screen.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeLibraryRepository implements LibraryRepository {
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
  }) async {
    return Ok(
      PagedResult(
        items: [
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
            createdAt: DateTime(2024, 1, 1),
            updatedAt: DateTime(2024, 6, 1),
            readingProgress: ReadingProgress(
              seriesId: 1,
              chapterId: 150,
              lastPage: 10,
              progressPct: 27.9,
              lastReadAt: DateTime(2024, 6, 1),
            ),
          ),
        ],
        total: 1,
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
  Future<Result<List<SeriesSummary>>> search(String query, {int page = 1}) async =>
      const Ok([]);

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
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) =>
      throw UnimplementedError();
}

Future<Widget> _buildTestApp() async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  return ProviderScope(
    overrides: [
      apiBaseUrlProvider.overrideWithValue('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(_FakeLibraryRepository()),
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
  });
}
