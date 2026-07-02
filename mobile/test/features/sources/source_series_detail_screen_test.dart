import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:aistudio_mobile/features/downloads/models/download_metrics.dart';
import 'package:aistudio_mobile/features/downloads/models/download_settings.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/providers/downloads_provider.dart';
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

class _FakeDownloadsNotifier extends DownloadsNotifier {
  _FakeDownloadsNotifier(this.fakeRepo, {this.items = const []});

  final DownloadsRepository fakeRepo;
  final List<DownloadItem> items;

  @override
  Future<DownloadsState> build() async {
    return DownloadsState(
      items: items,
      metrics: DownloadMetrics(
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
  }

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) {
    return fakeRepo.queueChapters(
      sourceId: sourceId,
      seriesId: seriesId,
      chapterIds: chapterIds,
      seriesTitle: seriesTitle,
      priority: priority,
    );
  }

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) {
    return fakeRepo.queueSeries(
      sourceId: sourceId,
      seriesId: seriesId,
      priority: priority,
    );
  }
}

class _RecordingDownloadsRepository implements DownloadsRepository {
  _RecordingDownloadsRepository({
    this.chaptersResponse = const Ok(QueueDownloadResponse(queued: [1], skipped: [])),
    this.seriesResponse = const Ok(QueueDownloadResponse(queued: [1, 2], skipped: ['ch-old'])),
    this.delay,
  });

  Result<QueueDownloadResponse> chaptersResponse;
  Result<QueueDownloadResponse> seriesResponse;
  Duration? delay;

  List<String>? lastChapterIds;
  bool queueSeriesCalled = false;
  int queueChaptersCallCount = 0;
  int queueSeriesCallCount = 0;

  @override
  Future<Result<QueueDownloadResponse>> queueChapters({
    required String sourceId,
    required String seriesId,
    required List<String> chapterIds,
    String? seriesTitle,
    int? priority,
  }) async {
    queueChaptersCallCount++;
    lastChapterIds = chapterIds;
    if (delay != null) {
      await Future<void>.delayed(delay!);
    }
    return chaptersResponse;
  }

  @override
  Future<Result<QueueDownloadResponse>> queueSeries({
    required String sourceId,
    required String seriesId,
    int? priority,
  }) async {
    queueSeriesCallCount++;
    queueSeriesCalled = true;
    if (delay != null) {
      await Future<void>.delayed(delay!);
    }
    return seriesResponse;
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
  List<DownloadItem> downloadItems = const [],
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
      downloadsProvider.overrideWith(
        () => _FakeDownloadsNotifier(fakeDownloadsRepo, items: downloadItems),
      ),
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
            downloadsRepositoryProvider.overrideWithValue(_RecordingDownloadsRepository()),
            downloadsProvider.overrideWith(() => _FakeDownloadsNotifier(_RecordingDownloadsRepository())),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      // Wait for series detail + chapters to resolve and render.
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final chaptersFinder = find.text('Chapters', skipOffstage: false);
      await tester.ensureVisible(chaptersFinder);
      await tester.pumpAndSettle();

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

      final downloadSelectedFinder = find.byKey(const Key('download-selected'), skipOffstage: false);
      await tester.ensureVisible(downloadSelectedFinder);
      await tester.pumpAndSettle();

      final selectedButton = tester.widget<OutlinedButton>(find.byKey(const Key('download-selected')));
      expect(selectedButton.onPressed, isNull);

      final checkboxFinder = find.byKey(const Key('select-manga-1:2'), skipOffstage: false);
      await tester.ensureVisible(checkboxFinder);
      await tester.pumpAndSettle();
      await tester.tap(checkboxFinder);
      await tester.pumpAndSettle();

      final enabledButton = tester.widget<OutlinedButton>(find.byKey(const Key('download-selected')));
      expect(enabledButton.onPressed, isNotNull);
    });

    testWidgets('Download Selected queues selected chapters and shows snackbar',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        chaptersResponse: const Ok(QueueDownloadResponse(
          queued: [1, 2],
          skipped: ['manga-1:3'],
        )),
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

      final ch1Checkbox = find.byKey(const Key('select-manga-1:1'), skipOffstage: false);
      await tester.ensureVisible(ch1Checkbox);
      await tester.pumpAndSettle();
      await tester.tap(ch1Checkbox);

      final ch2Checkbox = find.byKey(const Key('select-manga-1:2'), skipOffstage: false);
      await tester.ensureVisible(ch2Checkbox);
      await tester.pumpAndSettle();
      await tester.tap(ch2Checkbox);
      await tester.pumpAndSettle();

      final downloadButton = find.byKey(const Key('download-selected'), skipOffstage: false);
      await tester.ensureVisible(downloadButton);
      await tester.pumpAndSettle();
      await tester.tap(downloadButton);
      await tester.pumpAndSettle();

      expect(fakeDownloads.lastChapterIds, ['manga-1:1', 'manga-1:2']);
      expect(find.textContaining('Queued 2 chapters'), findsOneWidget);
      expect(find.textContaining('Skipped 1 already downloaded'), findsOneWidget);
      expect(find.text('Downloads'), findsOneWidget);
    });

    testWidgets('Download Series queues the series and shows snackbar',
        (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        seriesResponse: const Ok(QueueDownloadResponse(
          queued: [1, 2, 3],
          skipped: [],
        )),
      );
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final button = find.byKey(const Key('download-series'), skipOffstage: false);
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();
      await tester.tap(button);
      await tester.pumpAndSettle();

      expect(fakeDownloads.queueSeriesCalled, isTrue);
      expect(find.textContaining('Queued 3 chapters'), findsOneWidget);
    });

    testWidgets('per-chapter download button queues one chapter', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        chaptersResponse: const Ok(QueueDownloadResponse(queued: [9], skipped: [])),
      );
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final btn = find.byKey(const Key('download-manga-1:1'), skipOffstage: false);
      await tester.ensureVisible(btn);
      await tester.pumpAndSettle();
      await tester.tap(btn);
      await tester.pumpAndSettle();

      expect(fakeDownloads.lastChapterIds, ['manga-1:1']);
      expect(find.textContaining('Queued 1 chapter'), findsOneWidget);
    });

    testWidgets('snackbar Downloads action navigates to downloads screen',
        (tester) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        seriesResponse: const Ok(QueueDownloadResponse(
          queued: [1],
          skipped: [],
        )),
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
            path: Routes.downloads,
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
            downloadsProvider.overrideWith(() => _FakeDownloadsNotifier(fakeDownloads)),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final downloadSeriesButton = find.byKey(const Key('download-series'), skipOffstage: false);
      await tester.ensureVisible(downloadSeriesButton);
      await tester.pumpAndSettle();
      await tester.tap(downloadSeriesButton);
      await tester.pumpAndSettle();

      await tester.tap(find.text('Downloads'));
      await tester.pumpAndSettle();

      expect(navigatedLocation, Routes.downloads);
      expect(find.text('DOWNLOADS'), findsOneWidget);
    });

    testWidgets('ignores duplicate queue requests while pending', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        seriesResponse: const Ok(QueueDownloadResponse(queued: [1], skipped: [])),
        delay: const Duration(milliseconds: 50),
      );
      
      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final button = find.byKey(const Key('download-series'), skipOffstage: false);
      await tester.ensureVisible(button);
      await tester.pumpAndSettle();

      // Tap twice quickly
      await tester.tap(button, warnIfMissed: false);
      await tester.tap(button, warnIfMissed: false);
      
      // Wait for the async task to complete
      await tester.pumpAndSettle();

      expect(fakeDownloads.queueSeriesCallCount, 1);
      expect(find.textContaining('Queued 1 chapter'), findsOneWidget);
    });

    testWidgets('clears pending state and preserves selection on failure', (tester) async {
      final fakeUpdates = _FakeUpdatesRepository();
      final fakeDownloads = _RecordingDownloadsRepository(
        chaptersResponse: const Err(ApiError(
          statusCode: 500,
          code: 'queue_failed',
          message: 'Queue failed',
        )),
      );

      await _pumpScreen(
        tester,
        updatesRepo: fakeUpdates,
        downloadsRepo: fakeDownloads,
        chapters: [
          _chapter(id: 'manga-1:1', number: 1),
        ],
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // Select chapter
      final checkboxFinder = find.byKey(const Key('select-manga-1:1'), skipOffstage: false);
      await tester.ensureVisible(checkboxFinder);
      await tester.pumpAndSettle();
      await tester.tap(checkboxFinder);
      await tester.pumpAndSettle();

      // Tap download
      final downloadButton = find.byKey(const Key('download-selected'), skipOffstage: false);
      await tester.ensureVisible(downloadButton);
      await tester.pumpAndSettle();
      await tester.tap(downloadButton);
      
      await tester.pumpAndSettle();

      // Verify error snackbar
      expect(find.text('Queue failed'), findsOneWidget);

      // Clear snackbars so the next one shows immediately
      ScaffoldMessenger.of(tester.element(find.byType(SourceSeriesDetailScreen))).clearSnackBars();
      await tester.pumpAndSettle();
      
      // Verify selection is preserved (we can tap download again)
      expect(fakeDownloads.queueChaptersCallCount, 1);
      
      // Try again with success response
      fakeDownloads.chaptersResponse = const Ok(QueueDownloadResponse(queued: [1], skipped: []));
      await tester.tap(downloadButton);
      await tester.pumpAndSettle();

      expect(fakeDownloads.queueChaptersCallCount, 2);
      expect(find.textContaining('Queued 1 chapter'), findsOneWidget);
    });
  });

  group('SourceSeriesDetailScreen download status', () {
    DownloadItem _statusItem({
      required String chapterId,
      required String status,
    }) =>
        DownloadItem(
          id: chapterId.hashCode,
          source: 'mangadex',
          seriesId: 'manga-1',
          chapterId: chapterId,
          seriesTitle: 'Solo Leveling',
          chapterTitle: 'Chapter',
          status: status,
          progress: status == 'completed' ? 1 : 0.5,
          pagesDone: 5,
          pagesTotal: 10,
          bytesDownloaded: 1024,
          createdAt: DateTime.utc(2024, 1, 1),
          updatedAt: DateTime.utc(2024, 1, 2),
          priority: 0,
          retryCount: 0,
        );

    Future<void> _pumpWithStatuses(
      WidgetTester tester,
      List<DownloadItem> downloadItems,
    ) async {
      await _pumpScreen(
        tester,
        updatesRepo: _FakeUpdatesRepository(),
        chapters: [
          _chapter(id: 'manga-1:1', number: 1, title: 'Chapter 1'),
          _chapter(id: 'manga-1:2', number: 2, title: 'Chapter 2'),
          _chapter(id: 'manga-1:3', number: 3, title: 'Chapter 3'),
          _chapter(id: 'manga-1:4', number: 4, title: 'Chapter 4'),
          _chapter(id: 'manga-1:5', number: 5, title: 'Chapter 5'),
        ],
        downloadItems: downloadItems,
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
    }

    testWidgets('shows chapter download badges from downloads state', (tester) async {
      await _pumpWithStatuses(tester, [
        _statusItem(chapterId: 'manga-1:1', status: 'queued'),
        _statusItem(chapterId: 'manga-1:2', status: 'downloading'),
        _statusItem(chapterId: 'manga-1:3', status: 'completed'),
        _statusItem(chapterId: 'manga-1:4', status: 'failed'),
      ]);

      expect(find.text('Queued'), findsOneWidget);
      expect(find.text('Downloading'), findsOneWidget);
      expect(find.text('Completed'), findsOneWidget);
      expect(find.text('Failed'), findsOneWidget);
    });

    testWidgets('disables download for queued, downloading, and completed chapters',
        (tester) async {
      await _pumpWithStatuses(tester, [
        _statusItem(chapterId: 'manga-1:1', status: 'queued'),
        _statusItem(chapterId: 'manga-1:2', status: 'downloading'),
        _statusItem(chapterId: 'manga-1:3', status: 'completed'),
        _statusItem(chapterId: 'manga-1:4', status: 'failed'),
        _statusItem(chapterId: 'manga-1:5', status: 'cancelled'),
      ]);

      expect(
        tester.widget<IconButton>(find.byKey(const Key('download-manga-1:1'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<IconButton>(find.byKey(const Key('download-manga-1:2'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<IconButton>(find.byKey(const Key('download-manga-1:3'))).onPressed,
        isNull,
      );
      expect(
        tester.widget<IconButton>(find.byKey(const Key('download-manga-1:4'))).onPressed,
        isNotNull,
      );
      expect(
        tester.widget<IconButton>(find.byKey(const Key('download-manga-1:5'))).onPressed,
        isNotNull,
      );
    });

    testWidgets('failed chapter download button remains retryable', (tester) async {
      final fakeDownloads = _RecordingDownloadsRepository();
      await _pumpScreen(
        tester,
        updatesRepo: _FakeUpdatesRepository(),
        downloadsRepo: fakeDownloads,
        chapters: [_chapter(id: 'manga-1:4', number: 4, title: 'Chapter 4')],
        downloadItems: [
          DownloadItem(
            id: 44,
            source: 'mangadex',
            seriesId: 'manga-1',
            chapterId: 'manga-1:4',
            seriesTitle: 'Solo Leveling',
            chapterTitle: 'Chapter 4',
            status: 'failed',
            progress: 0.2,
            pagesDone: 2,
            pagesTotal: 10,
            bytesDownloaded: 512,
            createdAt: DateTime.utc(2024, 1, 1),
            updatedAt: DateTime.utc(2024, 1, 2),
            priority: 0,
            retryCount: 1,
          ),
        ],
      );

      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      final buttonFinder = find.byKey(const Key('download-manga-1:4'));
      expect(tester.widget<IconButton>(buttonFinder).onPressed, isNotNull);

      await tester.tap(buttonFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(fakeDownloads.lastChapterIds, ['manga-1:4']);
    });
  });
}
