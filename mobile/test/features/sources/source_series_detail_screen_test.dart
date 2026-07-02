import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository.dart';
import 'package:aistudio_mobile/features/sources/screens/source_series_detail_screen.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Minimal fake — only the series-detail + chapters paths are exercised; the
/// remaining methods throw so a stray call surfaces loudly rather than passing
/// silently with empty data.
class _FakeSourcesRepository implements SourcesRepository {
  _FakeSourcesRepository(this.series, this.chapters);

  final SourceSeriesSummary series;
  final List<SourceChapterSummary> chapters;

  @override
  Future<Result<SourceSeriesSummary>> getSeries(
    String sourceId,
    String seriesId,
  ) async =>
      Ok(series);

  @override
  Future<Result<List<SourceChapterSummary>>> getChapters(
    String sourceId,
    String seriesId,
  ) async =>
      Ok(chapters);

  @override
  Future<Result<List<SourceSummary>>> listSources() => throw UnimplementedError();

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<ReaderChapter>> getReaderChapter(
    String sourceId,
    String seriesId,
    String chapterId,
  ) =>
      throw UnimplementedError();
}

SourceSeriesSummary _series() => const SourceSeriesSummary(
      id: 'manga-1',
      sourceId: 'mangadex',
      title: 'Solo Leveling',
      chapterCount: 1,
      genres: [],
      coverUrl: 'http://example.test/cover.jpg',
    );

SourceChapterSummary _chapter({
  required String id,
  double? number,
  String title = 'Chapter 1',
}) =>
    SourceChapterSummary(
      id: id,
      sourceId: 'mangadex',
      seriesId: 'manga-1',
      title: title,
      number: number,
      pageCount: 10,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SourceSeriesDetailScreen chapter rows', () {
    testWidgets('tapping a chapter navigates to the source reader',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      final fakeRepo = _FakeSourcesRepository(
        _series(),
        [
          _chapter(id: 'manga-1:1', number: 1),
        ],
      );

      String? navigatedLocation;
      final router = GoRouter(
        initialLocation: '/sources/mangadex/series/manga-1',
        routes: [
          GoRoute(
            path: '/sources/:sourceId/series/:seriesId',
            builder: (_, state) => SourceSeriesDetailScreen(
              sourceId: state.pathParameters['sourceId']!,
              seriesId: state.pathParameters['seriesId']!,
            ),
          ),
          GoRoute(
            path: '/sources/:sourceId/series/:seriesId/chapters/:chapterId/read',
            builder: (_, state) {
              navigatedLocation = state.uri.toString();
              return const Scaffold(body: Center(child: Text('READER')));
            },
          ),
        ],
      );

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            sharedPrefsProvider.overrideWithValue(prefs),
            apiBaseUrlProvider.overrideWithValue('http://example.test'),
            sourcesRepositoryProvider.overrideWithValue(fakeRepo),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      // Wait for series detail + chapters to resolve and render.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Chapters'), findsOneWidget);

      // The chapter row label is "Chapter 1" (from chapterLabel).
      await tester.tap(find.text('Chapter 1'));
      await tester.pumpAndSettle();

      expect(navigatedLocation, isNotNull);
      expect(
        navigatedLocation,
        RoutePaths.sourceReader('mangadex', 'manga-1', 'manga-1:1'),
      );
      expect(find.text('READER'), findsOneWidget);
    });
  });
}
