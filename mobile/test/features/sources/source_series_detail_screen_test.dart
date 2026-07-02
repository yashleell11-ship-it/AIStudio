import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/reader/models/reader_chapter.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/repositories/sources_repository.dart';
import 'package:aistudio_mobile/features/sources/screens/source_series_detail_screen.dart';
import 'package:aistudio_mobile/features/updates/models/series_tracker.dart';
import 'package:aistudio_mobile/features/updates/models/update_notification.dart';
import 'package:aistudio_mobile/features/updates/repositories/updates_repository.dart';
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

/// Fake updates repository for the Follow button. Tracks whether
/// [followSeries] / [deleteTracker] were called so the test can assert the
/// correct endpoint is hit for each button state.
class _FakeUpdatesRepository implements UpdatesRepository {
  _FakeUpdatesRepository({this.trackers = const []});

  List<SeriesTracker> trackers;
  bool followCalled = false;
  int? deletedTrackerId;
  int deleteCallCount = 0;

  /// When set, [deleteTracker] awaits this before resolving, so tests can
  /// observe the button's busy/disabled state mid-flight and verify a
  /// second tap while pending does not fire a second delete.
  Completer<void>? deleteGate;

  @override
  Future<Result<void>> followSeries({
    required String source,
    required String seriesId,
    required String seriesTitle,
  }) async {
    followCalled = true;
    trackers = [
      ...trackers,
      SeriesTracker(
        id: 999,
        source: source,
        seriesId: seriesId,
        seriesTitle: seriesTitle,
        trackKind: TrackKind.followed,
        enabled: true,
        notify: true,
        autoDownload: false,
        knownChapterCount: 0,
      ),
    ];
    return const Ok(null);
  }

  @override
  Future<Result<void>> deleteTracker(int trackerId) async {
    deleteCallCount++;
    deletedTrackerId = trackerId;
    if (deleteGate != null) await deleteGate!.future;
    trackers = trackers.where((t) => t.id != trackerId).toList();
    return const Ok(null);
  }

  @override
  Future<Result<List<SeriesTracker>>> listTrackers() async => Ok(trackers);

  @override
  Future<Result<List<UpdateNotification>>> listNotifications({
    bool unreadOnly = false,
    int limit = 100,
  }) async =>
      const Ok([]);

  @override
  Future<Result<int>> getUnreadCount() async => const Ok(0);

  @override
  Future<Result<void>> markRead(int notificationId) async => const Ok(null);

  @override
  Future<Result<void>> markAllRead() async => const Ok(null);

  @override
  Future<Result<void>> triggerCheck() async => const Ok(null);
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

Future<ProviderContainer> _pumpScreen(
  WidgetTester tester, {
  required _FakeUpdatesRepository updatesRepo,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  final fakeSourcesRepo = _FakeSourcesRepository(
    _series(),
    [_chapter(id: 'manga-1:1', number: 1)],
  );

  final container = ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      apiBaseUrlProvider.overrideWithValue('http://example.test'),
      sourcesRepositoryProvider.overrideWithValue(fakeSourcesRepo),
      updatesRepositoryProvider.overrideWithValue(updatesRepo),
    ],
  );
  addTearDown(container.dispose);

  await tester.binding.setSurfaceSize(const Size(430, 932));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(
        home: SourceSeriesDetailScreen(
          sourceId: 'mangadex',
          seriesId: 'manga-1',
        ),
      ),
    ),
  );
  return container;
}

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
      final fakeUpdates = _FakeUpdatesRepository();

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
            updatesRepositoryProvider.overrideWithValue(fakeUpdates),
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

  group('SourceSeriesDetailScreen Follow button', () {
    testWidgets('shows Follow when the series is not followed', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      // Let the providers resolve.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Follow'), findsOneWidget);
      expect(find.text('Unfollow'), findsNothing);
      expect(fakeUpdates.followCalled, isFalse);
    });

    testWidgets('shows Unfollow when the series is already followed',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      );
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Unfollow'), findsOneWidget);
      expect(find.text('Follow'), findsNothing);
    });

    testWidgets('tapping Follow calls followSeries and flips to Unfollow',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Follow'), findsOneWidget);

      await tester.tap(find.text('Follow'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeUpdates.followCalled, isTrue);
      // After the optimistic + refresh cycle, the button should reflect the
      // new followed state.
      expect(find.text('Unfollow'), findsOneWidget);
    });

    testWidgets('tapping Unfollow calls deleteTracker', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      );
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Unfollow'), findsOneWidget);

      await tester.tap(find.text('Unfollow'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeUpdates.deletedTrackerId, 42);
    });

    testWidgets('unfollow disables the button while the delete is pending',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      )..deleteGate = Completer<void>();
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Unfollow'), findsOneWidget);

      await tester.tap(find.text('Unfollow'));
      await tester.pump();

      // Mirrors followSeries: actionPending flips immediately, before the
      // repo call resolves, so the button shows a busy label and disables.
      expect(find.text('Unfollowing…'), findsOneWidget);
      final button = tester.widget<FilledButton>(
        find.ancestor(
          of: find.text('Unfollowing…'),
          matching: find.byType(FilledButton),
        ),
      );
      expect(button.onPressed, isNull);

      fakeUpdates.deleteGate!.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Follow'), findsOneWidget);
    });

    testWidgets('double-tapping Unfollow while pending only calls deleteTracker once',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository(
        trackers: [
          const SeriesTracker(
            id: 42,
            source: 'mangadex',
            seriesId: 'manga-1',
            seriesTitle: 'Solo Leveling',
            trackKind: TrackKind.followed,
            enabled: true,
            notify: true,
            autoDownload: false,
            knownChapterCount: 0,
          ),
        ],
      )..deleteGate = Completer<void>();
      await _pumpScreen(tester, updatesRepo: fakeUpdates);

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Unfollow'));
      await tester.pump();
      expect(fakeUpdates.deleteCallCount, 1);

      // The button is disabled while pending, so this second tap must be a
      // no-op -- it must not fire a second deleteTracker call.
      await tester.tap(find.text('Unfollowing…'), warnIfMissed: false);
      await tester.pump();
      expect(fakeUpdates.deleteCallCount, 1);

      fakeUpdates.deleteGate!.complete();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeUpdates.deleteCallCount, 1);
    });
  });
}
