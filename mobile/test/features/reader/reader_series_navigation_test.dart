import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/reading_progress.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/providers/series_detail_provider.dart';
import 'package:manhwamaniacs/features/library/repositories/library_repository.dart';
import 'package:manhwamaniacs/features/library/screens/series_detail_screen.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/screens/reader_screen.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/screens/source_reader_screen.dart';
import 'package:manhwamaniacs/features/sources/screens/source_series_detail_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

// A connector series id with a `/` in it — the exact shape that forced
// RoutePaths to percent-encode. Every assertion below re-reads the id off the
// destination screen rather than off the location string, because go_router
// spells the same id encoded or decoded depending on how it was reached.
const _slashSeriesId = 'toonily/series-a';
const _slashChapterId = 'toonily/series-a/ch-1';

const _localSeriesId = 7;
const _localChapterId = 42;

const _localChapter = ChapterDetail(
  id: _localChapterId,
  seriesId: _localSeriesId,
  title: 'Chapter 1',
  pageCount: 2,
  pages: [
    PageInfo(
      id: 101,
      chapterId: _localChapterId,
      number: 1,
      filePath: '/pages/1.jpg',
      width: 800,
      height: 1200,
    ),
    PageInfo(
      id: 102,
      chapterId: _localChapterId,
      number: 2,
      filePath: '/pages/2.jpg',
      width: 800,
      height: 1200,
    ),
  ],
);

ReaderChapter _sourceChapter() => const ReaderChapter(
      id: _slashChapterId,
      seriesId: _slashSeriesId,
      title: 'Chapter 1',
      pageCount: 2,
      mode: ReaderMode.remote,
      sourceId: 'toonily',
      seriesTitle: 'Series A',
      pages: [
        ReaderPage(
          id: 'p1',
          number: 1,
          imageUrl: 'http://example.test/sources/toonily/pages/p1/image',
          width: 800,
          height: 1200,
        ),
        ReaderPage(
          id: 'p2',
          number: 2,
          imageUrl: 'http://example.test/sources/toonily/pages/p2/image',
          width: 800,
          height: 1200,
        ),
      ],
    );

/// The library reader flushes reading progress from its `dispose()` — which is
/// exactly what the jump to the series page triggers. Through the real
/// repository that becomes an HTTP request whose timeout Timer outlives the
/// test, so serve it locally instead. Every other call is out of scope here and
/// `noSuchMethod` says so loudly rather than quietly returning nothing.
class _ProgressOnlyLibraryRepository implements LibraryRepository {
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
          progressPct: 0,
          lastReadAt: DateTime.utc(2024),
        ),
      );

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Series-detail payloads are irrelevant here — only the route we land on is.
/// A completer that never completes parks each destination on its skeleton
/// without leaving a pending Timer behind to fail teardown.
List<Override> _pendingSeriesDetails() => [
      seriesDetailProvider(_localSeriesId)
          .overrideWith((ref) => Completer<SeriesDetail>().future),
      sourceSeriesDetailProvider(
        (sourceId: 'toonily', seriesId: _slashSeriesId),
      ).overrideWith((ref) => Completer<SourceSeriesDetailData>().future),
    ];

/// Mounts the real app — real router, real route table — so these tests prove
/// the routes the app actually ships, not a stand-in copy of them.
Future<ProviderContainer> _pumpApp(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(430, 932));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();

  final container = ProviderContainer(
    overrides: [
      apiBaseUrlOverride('http://example.test'),
      sharedPrefsProvider.overrideWithValue(prefs),
      libraryRepositoryProvider
          .overrideWithValue(_ProgressOnlyLibraryRepository()),
      authenticatedAuthOverride(),
      activeProfileOverride(),
      profileSessionReadyOverride(),
      readerChapterProvider(_localChapterId)
          .overrideWith((ref) async => _localChapter),
      adjacentChapterProvider((chapterId: _localChapterId, direction: 'previous'))
          .overrideWith((ref) async => null),
      adjacentChapterProvider((chapterId: _localChapterId, direction: 'next'))
          .overrideWith((ref) async => null),
      sourceReaderChapterProvider(
        (
          sourceId: 'toonily',
          seriesId: _slashSeriesId,
          chapterId: _slashChapterId,
        ),
      ).overrideWith((ref) async => _sourceChapter()),
      ..._pendingSeriesDetails(),
    ],
  );
  addTearDown(container.dispose);

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const ManhwaManiacsApp(),
    ),
  );
  await tester.pump();
  return container;
}

GoRouter _router(ProviderContainer container) =>
    container.read(appRouterProvider);

/// The matched route *pattern* rather than the location string: go_router
/// spells a slash-bearing series id encoded or decoded depending on whether the
/// route was reached by push or pop, but the pattern is stable either way.
String _fullPath(GoRouter router) =>
    router.routerDelegate.currentConfiguration.fullPath;

Future<void> _settleReader(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

/// Taps the chapter title in the reader's top bar — the affordance itself.
Future<void> _tapTitle(WidgetTester tester) async {
  await tester.tap(find.byTooltip('Go to series'));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Reader → series page', () {
    testWidgets('a local chapter lands on the library series route',
        (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      router.go(RoutePaths.reader(_localSeriesId, _localChapterId));
      await _settleReader(tester);
      expect(find.byType(ReaderScreen), findsOneWidget);

      await _tapTitle(tester);

      expect(_fullPath(router), Routes.seriesDetail);
      expect(find.byType(ReaderScreen), findsNothing);
      final series = tester.widget<SeriesDetailScreen>(
        find.byType(SeriesDetailScreen),
      );
      expect(series.seriesId, _localSeriesId);
    });

    testWidgets('a source chapter lands on the source series route with a '
        'slash-bearing id intact', (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      router.go(
        RoutePaths.sourceReader('toonily', _slashSeriesId, _slashChapterId),
      );
      await _settleReader(tester);
      expect(find.byType(SourceReaderScreen), findsOneWidget);

      await _tapTitle(tester);

      expect(_fullPath(router), Routes.sourceSeriesDetail);
      expect(find.byType(SourceReaderScreen), findsNothing);
      final series = tester.widget<SourceSeriesDetailScreen>(
        find.byType(SourceSeriesDetailScreen),
      );
      expect(series.sourceId, 'toonily');
      // The `/` survived RoutePaths' encoding and go_router's decoding — a raw
      // id here would have split into an extra path segment and 404'd.
      expect(series.seriesId, _slashSeriesId);
    });

    testWidgets('the more-options sheet offers the same jump', (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      router.go(RoutePaths.reader(_localSeriesId, _localChapterId));
      await _settleReader(tester);

      await tester.tap(find.byTooltip('Reader settings'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('Go to series'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));

      expect(_fullPath(router), Routes.seriesDetail);
      expect(find.byType(ReaderScreen), findsNothing);
    });
  });

  // The reader route sets `parentNavigatorKey: rootNavigatorKey`, so it renders
  // above the tab shell that owns both series screens. Pushing a shell route
  // from up there makes go_router append a second ShellRouteMatch carrying the
  // same page key, which Navigator asserts on — hence pop-when-beneath and
  // go-otherwise instead of an unconditional push.
  group('Reader → series page keeps the back stack sane', () {
    testWidgets('pops onto the series page already beneath instead of '
        'stacking a second copy', (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      // Exactly how the series screen opens a chapter: push the reader on top
      // of the live series page.
      router.go(RoutePaths.seriesDetail(_localSeriesId));
      await _settleReader(tester);
      unawaited(router.push(RoutePaths.reader(_localSeriesId, _localChapterId)));
      await _settleReader(tester);

      await _tapTitle(tester);

      expect(_fullPath(router), Routes.seriesDetail);
      // One copy, not two: the jump returned to the existing page.
      expect(
        find.byType(SeriesDetailScreen, skipOffstage: false),
        findsOneWidget,
      );

      // And the round trip is repeatable without the stack creeping upwards.
      unawaited(router.push(RoutePaths.reader(_localSeriesId, _localChapterId)));
      await _settleReader(tester);
      await _tapTitle(tester);

      expect(_fullPath(router), Routes.seriesDetail);
      expect(
        find.byType(SeriesDetailScreen, skipOffstage: false),
        findsOneWidget,
      );
    });

    testWidgets('still reaches the series page when the reader was opened from '
        'somewhere else, and leaves it poppable', (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      // Continue-reading on the dashboard pushes the reader straight from
      // /library, so the series page is not underneath it.
      router.go(Routes.library);
      await _settleReader(tester);
      unawaited(router.push(RoutePaths.reader(_localSeriesId, _localChapterId)));
      await _settleReader(tester);
      expect(find.byType(ReaderScreen), findsOneWidget);

      await _tapTitle(tester);

      expect(_fullPath(router), Routes.seriesDetail);
      expect(find.byType(SeriesDetailScreen), findsOneWidget);
      // Nested under the tab root, so back / the iOS edge-swipe still work.
      expect(router.canPop(), isTrue);
    });

    testWidgets('a source chapter opened from elsewhere keeps its slash-bearing '
        'id through the rebuilt route', (tester) async {
      final container = await _pumpApp(tester);
      final router = _router(container);

      // Not from the series page, so this takes the rebuild path — which parses
      // the encoded location afresh rather than returning to a live screen.
      router.go(Routes.sources);
      await _settleReader(tester);
      unawaited(
        router.push(
          RoutePaths.sourceReader('toonily', _slashSeriesId, _slashChapterId),
        ),
      );
      await _settleReader(tester);
      expect(find.byType(SourceReaderScreen), findsOneWidget);

      await _tapTitle(tester);

      expect(_fullPath(router), Routes.sourceSeriesDetail);
      final series = tester.widget<SourceSeriesDetailScreen>(
        find.byType(SourceSeriesDetailScreen),
      );
      expect(series.seriesId, _slashSeriesId);
      expect(router.canPop(), isTrue);
    });
  });
}
