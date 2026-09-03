import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloaded_series_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/screens/downloads_screen.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:mocktail/mocktail.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

class _MockDownloadsStore extends Mock implements DownloadsStore {}

class _FixedQueueController extends DownloadQueueController {
  _FixedQueueController(this._state);
  final DownloadQueueState _state;

  @override
  DownloadQueueState build() => _state;
}

SavedChapter _chapter({
  required int rowId,
  required String chapterKey,
  DownloadChapterState state = DownloadChapterState.complete,
  bool pinned = false,
  int bytes = 1024 * 1024,
  String? error,
}) =>
    SavedChapter(
      rowId: rowId,
      scopeId: 'u1p1',
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: chapterKey,
      chapterNumber: double.tryParse(chapterKey),
      title: null,
      seriesTitle: 'Solo Leveling',
      pageCount: 20,
      bytes: bytes,
      state: state,
      pinned: pinned,
      readAt: null,
      createdAt: DateTime.utc(2026),
      retryCount: 0,
      error: error,
    );

void main() {
  setUpAll(() {
    registerFallbackValue((sourceId: '', seriesKey: '', chapterKey: ''));
    registerFallbackValue((sourceId: '', seriesKey: ''));
  });

  Future<ProviderContainer> pumpScreen(
    WidgetTester tester, {
    List<DownloadedSeriesGroup> groups = const [],
    bool withScope = true,
    DownloadQueueState queueState = const DownloadQueueState(),
    DownloadsStore? store,
  }) async {
    SharedPreferences.setMockInitialValues(testPrefsDefaults());
    final prefs = await SharedPreferences.getInstance();

    final container = ProviderContainer(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        if (withScope) ...[
          authenticatedAuthOverride(),
          activeProfileOverride(),
        ],
        downloadedSeriesProvider.overrideWith((ref) async => groups),
        downloadQueueControllerProvider.overrideWith(() => _FixedQueueController(queueState)),
        if (store != null) downloadsStoreProvider.overrideWithValue(store),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: Routes.downloads,
            routes: [
              GoRoute(
                path: Routes.downloads,
                builder: (context, state) => const DownloadsScreen(),
              ),
              GoRoute(
                path: '/library/read/:sourceId/:seriesKey/:chapterKey',
                builder: (context, state) => const Scaffold(body: Text('Reader')),
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    return container;
  }

  testWidgets('shows an empty state with nothing downloaded', (tester) async {
    await pumpScreen(tester);
    expect(find.text('No downloads yet'), findsOneWidget);
  });

  testWidgets('shows the no-profile state without an active scope', (tester) async {
    await pumpScreen(tester, withScope: false);
    expect(find.text('No active profile'), findsOneWidget);
    expect(find.text('No downloads yet'), findsNothing);
  });

  testWidgets('lists a series collapsed, with real byte totals', (tester) async {
    final group = DownloadedSeriesGroup(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      seriesTitle: 'Solo Leveling',
      chapters: [
        _chapter(rowId: 1, chapterKey: '1', bytes: 2 * 1024 * 1024),
        _chapter(rowId: 2, chapterKey: '2'),
      ],
    );
    await pumpScreen(tester, groups: [group]);

    expect(find.text('Solo Leveling'), findsOneWidget);
    expect(find.text('2 chapters · 3.0 MB'), findsOneWidget);
    // Collapsed by default — chapter rows are not built yet.
    expect(find.text('Downloaded'), findsNothing);
  });

  testWidgets('expanding a series shows its chapters and their state',
      (tester) async {
    final group = DownloadedSeriesGroup(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      seriesTitle: 'Solo Leveling',
      chapters: [
        _chapter(rowId: 1, chapterKey: '1'),
        _chapter(rowId: 2, chapterKey: '2', state: DownloadChapterState.failed, error: 'offline'),
      ],
    );
    await pumpScreen(tester, groups: [group]);

    await tester.tap(find.text('Solo Leveling'));
    await tester.pump();

    expect(find.textContaining('Downloaded'), findsOneWidget);
    expect(find.textContaining('Failed — offline'), findsOneWidget);
  });

  testWidgets('pinning a series calls the store and refreshes the list',
      (tester) async {
    final store = _MockDownloadsStore();
    when(
      () => store.setSeriesPinned(
        series: any(named: 'series'),
        pinned: any(named: 'pinned'),
      ),
    ).thenAnswer((_) async {});
    final group = DownloadedSeriesGroup(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      seriesTitle: 'Solo Leveling',
      chapters: [_chapter(rowId: 1, chapterKey: '1')],
    );
    await pumpScreen(tester, groups: [group], store: store);

    await tester.tap(find.byKey(const Key('pin-series-asura-solo-leveling')));
    await tester.pump();

    verify(
      () => store.setSeriesPinned(
        series: (sourceId: 'asura', seriesKey: 'solo-leveling'),
        pinned: true,
      ),
    ).called(1);
  });

  testWidgets('removing a chapter calls deleteDownload', (tester) async {
    final store = _MockDownloadsStore();
    when(() => store.deleteDownload(any())).thenAnswer((_) async {});
    final group = DownloadedSeriesGroup(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      seriesTitle: 'Solo Leveling',
      chapters: [_chapter(rowId: 1, chapterKey: '1')],
    );
    await pumpScreen(tester, groups: [group], store: store);

    await tester.tap(find.text('Solo Leveling'));
    await tester.pump();
    await tester.tap(find.byKey(const Key('remove-asura-solo-leveling-1')));
    await tester.pump();

    verify(
      () => store.deleteDownload(
        (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: '1'),
      ),
    ).called(1);
  });

  testWidgets('shows the paused-at-cap banner', (tester) async {
    await pumpScreen(
      tester,
      queueState: const DownloadQueueState(
        pauseReason: DownloadQueuePauseReason.cap,
      ),
    );

    expect(find.textContaining('storage cap'), findsOneWidget);
  });
}
