import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_data.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_stats.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/library/providers/dashboard_providers.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/features/library/screens/dashboard_screen.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeLibraryRepository implements LibraryRepository {
  _FakeLibraryRepository(this.data);

  final DashboardData data;
  bool shouldFail = false;

  @override
  Future<Result<List<ContinueReadingItem>>> continueReading({int limit = 20}) async {
    if (shouldFail) {
      return const Err(UnknownError(message: 'network failure'));
    }
    return Ok(data.continueReading.take(limit).toList());
  }

  @override
  Future<Result<List<SeriesSummary>>> recentlyUpdated({int limit = 20}) async {
    if (shouldFail) {
      return const Err(UnknownError(message: 'network failure'));
    }
    return Ok(data.recentlyUpdated.take(limit).toList());
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
  }) async {
    if (shouldFail) {
      return const Err(UnknownError(message: 'network failure'));
    }
    return Ok(
      PagedResult(
        items: data.recentlyUpdated,
        total: data.stats.totalSeries,
        page: page,
        perPage: perPage,
        hasNext: false,
      ),
    );
  }

  @override
  Future<Result<void>> deleteProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) => throw UnimplementedError();

  @override
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

  @override
  Future<Result<List<Collection>>> listCollections() => throw UnimplementedError();

  @override
  Future<Result<List<Tag>>> listTags() => throw UnimplementedError();

  @override
  Future<Result<List<SeriesSummary>>> recentlyAdded({int limit = 20}) =>
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
  Future<Result<void>> toggleFavorite(int seriesId) => throw UnimplementedError();
}

SeriesSummary _sampleSeries(int id) {
  return SeriesSummary(
    id: id,
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
  );
}

DashboardData _sampleDashboard() {
  return DashboardData(
    recentlyUpdated: [_sampleSeries(1), _sampleSeries(2)],
    continueReading: [
      ContinueReadingItem(
        seriesId: 1,
        seriesTitle: 'Solo Leveling',
        chapterId: 150,
        chapterTitle: 'Chapter 150',
        lastPage: 10,
        progressPct: 27.9,
        lastReadAt: DateTime.now(),
      ),
    ],
    stats: const DashboardStats(
      totalSeries: 2,
      totalChapters: 358,
      totalPages: 7160,
      readingStreakDays: 1,
    ),
  );
}

Future<Widget> _buildTestApp({
  required DashboardData data,
  bool shouldFail = false,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  final fakeRepo = _FakeLibraryRepository(data)..shouldFail = shouldFail;

  return ProviderScope(
    overrides: [
      apiBaseUrlProvider.overrideWithValue('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider.overrideWithValue(fakeRepo),
      dashboardProvider.overrideWith((ref) async {
        if (shouldFail) throw const UnknownError(message: 'network failure');
        return data;
      }),
    ],
    child: const MaterialApp(
      home: DashboardScreen(),
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('DashboardScreen', () {
    testWidgets('renders dashboard sections with data', (tester) async {
      await tester.pumpWidget(await _buildTestApp(data: _sampleDashboard()));
      await tester.pumpAndSettle();

      expect(find.text('AIStudio'), findsWidgets);
      expect(find.text('Recently Updated'), findsOneWidget);
      expect(find.text('Continue Reading'), findsWidgets);
      expect(find.text('Total Comics'), findsOneWidget);
      expect(find.text('Solo Leveling'), findsWidgets);
    });

    testWidgets('shows empty state when library is empty', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          data: const DashboardData(
            recentlyUpdated: [],
            continueReading: [],
            stats: DashboardStats(
              totalSeries: 0,
              totalChapters: 0,
              totalPages: 0,
              readingStreakDays: 0,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Your library is empty'), findsOneWidget);
    });

    testWidgets('shows error state on failure', (tester) async {
      await tester.pumpWidget(
        await _buildTestApp(
          data: _sampleDashboard(),
          shouldFail: true,
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Could not load dashboard'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);
    });
  });
}
