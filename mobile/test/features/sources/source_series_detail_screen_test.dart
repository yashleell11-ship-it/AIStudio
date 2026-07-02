import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/repositories/downloads_repository.dart';
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

class _RecordingDownloadsRepository implements DownloadsRepository {
  _RecordingDownloadsRepository({
    this.chaptersResponse = const QueueDownloadResponse(queued: [1], skipped: []),
    this.seriesResponse = const QueueDownloadResponse(queued: [1, 2], skipped: ['ch-old']),
  });

  QueueDownloadResponse chaptersResponse;
  QueueDownloadResponse seriesResponse;

  List<String>? lastChapterIds;
  bool queueSeriesCalled = false;

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) async {
    lastChapterIds = chapterIds;
    return Ok(chaptersResponse);
  }

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) async {
    queueSeriesCalled = true;
    return Ok(seriesResponse);
  }

  @override
  Future<Result<List<DownloadItem>>> listDownloads() async => const Ok([]);

  @override
  Future<Result<DownloadMetrics>> getMetrics() async => Ok(
        DownloadMetrics(
          total: 0,
          completed: 0,
          failed: 0,
          remaining: 0,
          active: 0,
          queued: 0,
          paused: 0,
          storageUsedBytes: 0,
          storageFreeBytes: 0,
          overallSpeedBps: 0,
          overallSpeedMbps: 0,
          overallEtaSeconds: null,
          workers: const DownloadWorkers(configured: 1, active: 0, running: 0),
        ),
      );

  @override
  Future<Result<DownloadSettings>> getSettings() => throw UnimplementedError();

  @override
  Future<Result<DownloadSettings>> updateSettings(DownloadSettings settings) =>
      throw UnimplementedError();

  @override
  Future<Result<void>> pauseDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> resumeDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> cancelDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<void>> retryDownload(int downloadId) => throw UnimplementedError();

  @override
  Future<Result<int>> pauseAll() => throw UnimplementedError();

  @override
  Future<Result<int>> resumeAll() => throw UnimplementedError();

  @override
  Future<Result<int>> cancelAll() => throw UnimplementedError();

  @override
  Future<Result<int>> pauseSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> resumeSeries({
    required String sourceId,
    required String seriesId,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<int>> cancelSeries({
    required String sourceId,
    required String seriesId,
  }) =>
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

Future<ProviderContainer> _pumpScreen(
  WidgetTester tester, {
  required _FakeUpdatesRepository updatesRepo,
  _RecordingDownloadsRepository? downloadsRepo,
  List<SourceChapterSummary>? chapters,
}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  final fakeSourcesRepo = _FakeSourcesRepository(
    _series(),
    chapters ?? [_chapter(id: 'manga-1:1', number: 1)],
  );
  final fakeDownloadsRepo = downloadsRepo ?? _RecordingDownloadsRepository();

  final container = ProviderContainer(
    overrides: [
      sharedPrefsProvider.overrideWithValue(prefs),
      apiBaseUrlProvider.overrideWithValue('http://example.test'),
      sourcesRepositoryProvider.overrideWithValue(fakeSourcesRepo),
      updatesRepositoryProvider.overrideWithValue(updatesRepo),
      downloadsRepositoryProvider.overrideWithValue(fakeDownloadsRepo),
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

  group('SourceSeriesDetailScreen download actions', () {
    testWidgets('Download Selected stays disabled until a chapter is selected',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        chapters: [
          _chapter(id: 'manga-1:1', number: 1, title: 'Chapter 1'),
          _chapter(id: 'manga-1:2', number: 2, title: 'Chapter 2'),
        ],
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final selectedButton = tester.widget<OutlinedButton>(
        find.byKey(const Key('download-selected')),
      );
      expect(selectedButton.onPressed, isNull);

      await tester.tap(find.byKey(const Key('select-manga-1:2')));
      await tester.pump();

      final enabledButton = tester.widget<OutlinedButton>(
        find.byKey(const Key('download-selected')),
      );
      expect(enabledButton.onPressed, isNotNull);
    });

    testWidgets('Download Selected queues selected chapters and shows snackbar',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        chaptersResponse: const QueueDownloadResponse(
          queued: [1, 2],
          skipped: ['manga-1:3'],
        ),
      );
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
        chapters: [
          _chapter(id: 'manga-1:1', number: 1, title: 'Chapter 1'),
          _chapter(id: 'manga-1:2', number: 2, title: 'Chapter 2'),
        ],
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(const Key('select-manga-1:1')));
      await tester.tap(find.byKey(const Key('select-manga-1:2')));
      await tester.pump();

      await tester.tap(find.byKey(const Key('download-selected')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeDownloads.lastChapterIds, ['manga-1:1', 'manga-1:2']);
      expect(find.text('Queued 2 chapters'), findsOneWidget);
      expect(find.text('Skipped 1 already downloaded'), findsOneWidget);
      expect(find.text('Downloads'), findsOneWidget);
    });

    testWidgets('Download Series queues the series and shows snackbar',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        seriesResponse: const QueueDownloadResponse(
          queued: [1, 2, 3],
          skipped: [],
        ),
      );
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(const Key('download-series')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeDownloads.queueSeriesCalled, isTrue);
      expect(find.text('Queued 3 chapters'), findsOneWidget);
    });

    testWidgets('per-chapter download button queues one chapter', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        chaptersResponse: const QueueDownloadResponse(queued: [9], skipped: []),
      );
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(const Key('download-manga-1:1')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeDownloads.lastChapterIds, ['manga-1:1']);
      expect(find.text('Queued 1 chapter'), findsOneWidget);
    });

    testWidgets('snackbar Downloads action navigates to downloads screen',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository();

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
            path: RoutePaths.downloads,
            builder: (_, state) {
              navigatedLocation = state.uri.toString();
              return const Scaffold(body: Center(child: Text('DOWNLOADS')));
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
            sourcesRepositoryProvider.overrideWithValue(
              _FakeSourcesRepository(
                _series(),
                [_chapter(id: 'manga-1:1', number: 1)],
              ),
            ),
            updatesRepositoryProvider.overrideWithValue(fakeUpdates),
            downloadsRepositoryProvider.overrideWithValue(fakeDownloads),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.byKey(const Key('download-series')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      await tester.tap(find.text('Downloads'));
      await tester.pumpAndSettle();

      expect(navigatedLocation, RoutePaths.downloads);
      expect(find.text('DOWNLOADS'), findsOneWidget);
    });
  });
}
