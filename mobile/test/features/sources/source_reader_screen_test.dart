import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/chapter.dart';
import 'package:aistudio_mobile/features/library/repositories/library_repository.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/reading_history_item.dart';
import 'package:aistudio_mobile/features/library/models/reading_progress.dart';
import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/models/tag.dart';
import 'package:aistudio_mobile/features/reader/models/adjacent_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/reader/models/reader_page.dart';
import 'package:aistudio_mobile/features/reader/screens/reader_screen.dart';
import 'package:aistudio_mobile/features/sources/providers/source_reader_provider.dart';
import 'package:aistudio_mobile/features/sources/screens/source_reader_screen.dart';
import '../../support/test_overrides.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

ReaderChapter _onlineChapter({
  String? previousChapterId,
  String? nextChapterId,
}) {
  return ReaderChapter(
    id: 'manga-1:1',
    seriesId: 'manga-1',
    title: 'Chapter 1',
    pageCount: 2,
    mode: ReaderMode.remote,
    sourceId: 'mangadex',
    seriesTitle: 'Solo Leveling',
    previousChapterId: previousChapterId,
    nextChapterId: nextChapterId,
    pages: const [
      ReaderPage(
        id: 'manga-1:1:1',
        number: 1,
        imageUrl: 'http://example.test/sources/mangadex/pages/p1/image',
        width: 800,
        height: 1200,
      ),
      ReaderPage(
        id: 'manga-1:1:2',
        number: 2,
        imageUrl: 'http://example.test/sources/mangadex/pages/p2/image',
        width: 800,
        height: 1200,
      ),
    ],
  );
}

ReaderChapter _localChapter({
  int librarySeriesId = 7,
  int libraryChapterId = 42,
  String? previousChapterId,
  String? nextChapterId,
}) {
  return ReaderChapter(
    id: libraryChapterId.toString(),
    seriesId: librarySeriesId.toString(),
    title: 'Chapter 1',
    pageCount: 2,
    mode: ReaderMode.local,
    previousChapterId: previousChapterId,
    nextChapterId: nextChapterId,
    pages: const [
      ReaderPage(
        id: '101',
        number: 1,
        imageUrl: 'http://example.test/reader/page/101/image',
        width: 800,
        height: 1200,
      ),
      ReaderPage(
        id: '102',
        number: 2,
        imageUrl: 'http://example.test/reader/page/102/image',
        width: 800,
        height: 1200,
      ),
    ],
  );
}

GoRouter _router(Widget child) => GoRouter(
      routes: [GoRoute(path: '/', builder: (_, __) => child)],
    );

class _LocalReaderRepository implements LibraryRepository {
  @override
  Future<Result<ChapterDetail>> getChapter(int chapterId) async => Ok(
        ChapterDetail(
          id: chapterId,
          seriesId: 7,
          title: 'Chapter 1',
          pageCount: 2,
          pages: const [
            PageInfo(
              id: 101,
              chapterId: 42,
              number: 1,
              filePath: '/pages/1.jpg',
              width: 800,
              height: 1200,
            ),
            PageInfo(
              id: 102,
              chapterId: 42,
              number: 2,
              filePath: '/pages/2.jpg',
              width: 800,
              height: 1200,
            ),
          ],
        ),
      );

  @override
  Future<Result<AdjacentChapter?>> getAdjacentChapter(
    int chapterId, {
    required String direction,
  }) async {
    if (direction == 'next') {
      return const Ok(AdjacentChapter(id: 43, seriesId: 7, title: 'Chapter 2'));
    }
    return const Ok(null);
  }

  @override
  Future<Result<ReadingProgress>> saveProgress({
    required int seriesId,
    required int chapterId,
    required int lastPage,
  }) async =>
      Ok(
        ReadingProgress(
          seriesId: seriesId,
          chapterId: chapterId,
          lastPage: lastPage,
          progressPct: 50,
          lastReadAt: DateTime.utc(2024, 1, 1),
        ),
      );

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
  Future<Result<ReadingProgress?>> getProgress(int seriesId) => throw UnimplementedError();

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

Widget _wrap(
  List<Override> overrides,
  Widget child,
) {
  return ProviderScope(
    overrides: overrides,
    child: MaterialApp.router(routerConfig: _router(child)),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SourceReaderScreen', () {
    testWidgets('shows loading skeleton while fetching', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      // A completer that is never completed keeps the provider pending without
      // leaving a Timer alive (a Future.delayed would, failing test teardown).
      final completer = Completer<ReaderChapter>();

      await tester.pumpWidget(
        _wrap(
          [
            sharedPrefsProvider.overrideWithValue(prefs),
            sourceReaderChapterProvider((
              sourceId: 'mangadex',
              seriesId: 'manga-1',
              chapterId: 'manga-1:1',
            )).overrideWith((ref) => completer.future),
          ],
          const SourceReaderScreen(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterId: 'manga-1:1',
          ),
        ),
      );

      // First frame starts the future; skeleton renders immediately.
      await tester.pump();
      expect(find.text('Loading chapter…'), findsOneWidget);
    });

    testWidgets('renders online chapter title, pages and hides bookmark',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          [
            sharedPrefsProvider.overrideWithValue(prefs),
            sourceReaderChapterProvider((
              sourceId: 'mangadex',
              seriesId: 'manga-1',
              chapterId: 'manga-1:1',
            )).overrideWith((ref) async => _onlineChapter()),
          ],
          const SourceReaderScreen(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterId: 'manga-1:1',
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Chapter 1'), findsOneWidget);
      expect(find.textContaining('Page 1 / 2'), findsOneWidget);
      // Online reader never offers bookmarks.
      expect(find.text('Save'), findsNothing);
    });

    testWidgets('enables prev/next buttons when payload provides chapter ids',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.binding.setSurfaceSize(const Size(430, 932));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _wrap(
          [
            sharedPrefsProvider.overrideWithValue(prefs),
            sourceReaderChapterProvider((
              sourceId: 'mangadex',
              seriesId: 'manga-1',
              chapterId: 'manga-1:1',
            )).overrideWith(
              (ref) async => _onlineChapter(
                previousChapterId: 'manga-1:0',
                nextChapterId: 'manga-1:2',
              ),
            ),
          ],
          const SourceReaderScreen(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterId: 'manga-1:1',
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final prevButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Prev'),
          matching: find.byType(TextButton),
        ),
      );
      final nextButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Next'),
          matching: find.byType(TextButton),
        ),
      );
      expect(prevButton.enabled, isTrue);
      expect(nextButton.enabled, isTrue);
    });

    testWidgets('shows retry state on load failure', (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();

      await tester.pumpWidget(
        _wrap(
          [
            sharedPrefsProvider.overrideWithValue(prefs),
            sourceReaderChapterProvider((
              sourceId: 'mangadex',
              seriesId: 'manga-1',
              chapterId: 'manga-1:1',
            )).overrideWith((ref) async {
              throw Exception('network failure');
            }),
          ],
          const SourceReaderScreen(
            sourceId: 'mangadex',
            seriesId: 'manga-1',
            chapterId: 'manga-1:1',
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Retry'), findsOneWidget);
      expect(find.text('Go back'), findsOneWidget);
    });

    testWidgets('redirects local payload to library reader with progress controls',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      String? navigatedLocation;

      final router = GoRouter(
        initialLocation: RoutePaths.sourceReader('mangadex', 'manga-1', 'manga-1:1'),
        routes: [
          GoRoute(
            path: '/sources/:sourceId/series/:seriesId/chapters/:chapterId/read',
            builder: (_, state) => SourceReaderScreen(
              sourceId: state.pathParameters['sourceId']!,
              seriesId: state.pathParameters['seriesId']!,
              chapterId: state.pathParameters['chapterId']!,
            ),
          ),
          GoRoute(
            path: '/library/:seriesId/chapters/:chapterId/read',
            builder: (_, state) {
              navigatedLocation = state.uri.toString();
              return ReaderScreen(
                seriesId: int.parse(state.pathParameters['seriesId']!),
                chapterId: int.parse(state.pathParameters['chapterId']!),
              );
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
            apiBaseUrlOverride('http://example.test'),
            libraryRepositoryProvider.overrideWithValue(_LocalReaderRepository()),
            sourceReaderChapterProvider((
              sourceId: 'mangadex',
              seriesId: 'manga-1',
              chapterId: 'manga-1:1',
            )).overrideWith((ref) async => _localChapter()),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump();
      expect(navigatedLocation, '/library/7/chapters/42/read');
      expect(find.text('Save'), findsOneWidget);

      final nextButton = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Next'),
          matching: find.byType(TextButton),
        ),
      );
      expect(nextButton.enabled, isTrue);
    });
  });
}
