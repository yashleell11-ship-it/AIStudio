import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/app.dart';
import 'package:manhwamaniacs/app/router/app_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/config/env.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/active_download_queue_provider.dart';
import 'package:manhwamaniacs/features/downloads/screens/downloads_screen.dart';
import 'package:manhwamaniacs/features/more/screens/more_screen.dart';
import 'package:manhwamaniacs/features/settings/providers/app_update_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Downloads used to be a row inside More — an offline library reachable only
/// by going looking for it. These cover the promotion: it is a tab root of
/// its own, it keeps the shell chrome, and an active queue announces itself
/// from wherever the user happens to be.
SavedChapter _queued(int rowId) => SavedChapter(
      rowId: rowId,
      scopeId: 'u1p1',
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: '$rowId',
      chapterNumber: rowId.toDouble(),
      title: null,
      seriesTitle: 'Solo Leveling',
      pageCount: 20,
      bytes: 0,
      state: DownloadChapterState.queued,
      pinned: false,
      readAt: null,
      createdAt: DateTime.utc(2026),
      retryCount: 0,
      error: null,
    );

Future<ProviderContainer> _pumpApp(
  WidgetTester tester, {
  List<SavedChapter> queue = const [],
}) async {
  await tester.binding.setSurfaceSize(const Size(600, 2000));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  final prefs = await SharedPreferences.getInstance();

  final container = ProviderContainer(
    overrides: [
      apiBaseUrlOverride(Env.defaultApiUrl),
      sharedPrefsProvider.overrideWithValue(prefs),
      authenticatedAuthOverride(),
      activeProfileOverride(),
      ...noDownloadsStoreOverrides(),
      profileSessionReadyOverride(),
      appUpdateProvider.overrideWith((ref) async => null),
      activeDownloadQueueProvider.overrideWith((ref) async => queue),
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
  await tester.pump(const Duration(milliseconds: 400));
  return container;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Downloads is a bottom-nav destination, alongside the old four',
      (tester) async {
    await _pumpApp(tester);

    final bar = tester.widget<NavigationBar>(find.byType(NavigationBar));
    expect(
      bar.destinations
          .cast<NavigationDestination>()
          .map((d) => d.label)
          .toList(),
      // Nothing the owner already uses was displaced to make room.
      ['Library', 'Sources', 'Search', 'Downloads', 'More'],
    );
  });

  testWidgets('tapping it opens the Downloads screen inside the shell',
      (tester) async {
    await _pumpApp(tester);

    await tester.tap(find.text('Downloads'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(DownloadsScreen), findsOneWidget);
    // Still a tab, not a pushed page: the nav bar stays put.
    expect(find.byType(NavigationBar), findsOneWidget);
  });

  testWidgets('More no longer offers a second way in', (tester) async {
    final container = await _pumpApp(tester);
    container.read(appRouterProvider).go(Routes.more);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    expect(find.byType(MoreScreen), findsOneWidget);
    // Storage is still there — only the duplicate Downloads row went.
    expect(find.text('Storage'), findsOneWidget);
    expect(
      find.descendant(
        of: find.byType(MoreScreen),
        matching: find.text('Downloads'),
      ),
      findsNothing,
    );
  });

  testWidgets('a queue with work shows a count badge from any tab',
      (tester) async {
    await _pumpApp(tester, queue: [_queued(1), _queued(2), _queued(3)]);

    // Still on Library — the point is that the queue is visible from here.
    expect(find.byType(DownloadsScreen), findsNothing);
    final badge = tester.widget<Badge>(find.byType(Badge));
    expect(badge.isLabelVisible, isTrue);
    expect(find.text('3'), findsOneWidget);
  });

  testWidgets('an idle queue shows no badge', (tester) async {
    await _pumpApp(tester);
    final badge = tester.widget<Badge>(find.byType(Badge));
    expect(badge.isLabelVisible, isFalse);
  });
}
