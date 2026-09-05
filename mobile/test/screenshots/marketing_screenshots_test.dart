@Tags(['screenshots'])
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/app/theme/app_theme.dart';
import 'package:manhwamaniacs/app/theme/preset_controller.dart';
import 'package:manhwamaniacs/app/theme/theme_controller.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/screens/dashboard_screen.dart';
import 'package:manhwamaniacs/features/library/screens/statistics_screen.dart';

import 'package:manhwamaniacs/features/settings/screens/theme_gallery_screen.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../support/test_overrides.dart';
import 'support/shot_covers.dart';
import 'support/shot_fixtures.dart';
import 'support/shot_harness.dart';
import 'support/shot_network.dart';

/// Regenerates the marketing screenshots served on the install page.
///
/// Run it deliberately:
///
/// ```sh
/// cd mobile
/// MM_WRITE_SHOTS=1 flutter test test/screenshots/marketing_screenshots_test.dart
/// ```
///
/// Without `MM_WRITE_SHOTS` the same screens are still built, pumped and
/// rasterised — so a screen that stops rendering fails here — but nothing is
/// written, which keeps an ordinary `flutter test` from dirtying the working
/// tree.
///
/// Output lands in `mobile/docs/screenshots/`, which the deploy mounts into
/// the backend container and `backend/routes/app_distribution.py` serves under
/// `/app/media`. The filenames are load-bearing: the `_SHOWCASE` list in that
/// file names each one, and its captions describe these exact frames.
///
/// Everything on screen comes from `support/shot_fixtures.dart` and
/// `support/shot_covers.dart` — invented series, cover art painted in-repo.
/// That is a requirement, not a shortcut: the install page is public and the
/// app carries mature sources, so no real source, series or artwork may reach
/// it. Fixtures make that a property of the code rather than a promise.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(loadAppFonts);
  setUpAll(setUpShotCoverCache);

  testWidgets('library — the followed shelf', (tester) async {
    useShotViewport(tester);
    await paintCovers(tester, shotManga);
    final prefs = await shotPrefs();

    final key = GlobalKey();
    await tester.pumpWidget(
      _shotApp(
        key: key,
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          ...contentModeOverrides(),
          _shelfSource(novels: false),
          _followedOverride(shotManga),
        ],
        child: const DashboardScreen(),
      ),
    );
    await settleShot(tester);
    await pumpUntilCoversLoad(tester);
    await settleShot(tester);

    expect(find.text('The Lantern Courier'), findsOneWidget);
    expect(find.text('9 series followed'), findsOneWidget);
    await maybeWriteShot(tester, find.byKey(key), 'shot-library.png');
    await drainCacheTimers(tester);
  });

  testWidgets('novels — the same library, as books', (tester) async {
    useShotViewport(tester);
    await paintCovers(tester, shotNovels);
    final prefs = await shotPrefs();

    final key = GlobalKey();
    await tester.pumpWidget(
      _shotApp(
        key: key,
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          ...contentModeOverrides(
            mode: ContentMode.novel,
            novelsEnabled: true,
          ),
          _shelfSource(novels: true),
          _followedOverride(shotNovels),
        ],
        child: const DashboardScreen(),
      ),
    );
    await settleShot(tester);
    // Twice: the shelf only exists once the content-mode scope has resolved,
    // so the first pass is spent getting the rows built, not their covers.
    await pumpUntilCoversLoad(tester);
    await settleShot(tester);
    await pumpUntilCoversLoad(tester);
    await settleShot(tester);

    expect(find.text('The Salt Road Chronicles'), findsOneWidget);
    await maybeWriteShot(tester, find.byKey(key), 'shot-novels.png');
    await drainCacheTimers(tester);
  });

  testWidgets('statistics — what the reading actually looks like',
      (tester) async {
    useShotViewport(tester);
    await paintCovers(tester, shotManga);
    final prefs = await shotPrefs();

    final key = GlobalKey();
    await tester.pumpWidget(
      _shotApp(
        key: key,
        overrides: [
          sharedPrefsProvider.overrideWithValue(prefs),
          statisticsProvider.overrideWith((ref) async => shotStatistics()),
        ],
        child: const StatisticsScreen(),
      ),
    );
    await settleShot(tester);
    // "Most read" carries covers, and so brings the cache manager (and its
    // deferred cleanup timer) with it.
    await pumpUntilCoversLoad(tester);
    await settleShot(tester);

    expect(find.textContaining('day'), findsWidgets);
    await maybeWriteShot(tester, find.byKey(key), 'shot-statistics.png');
    await drainCacheTimers(tester);
  });

  testWidgets('themes — the palette gallery', (tester) async {
    useShotViewport(tester);
    final prefs = await shotPrefs();

    final key = GlobalKey();
    await tester.pumpWidget(
      _shotApp(
        key: key,
        overrides: [sharedPrefsProvider.overrideWithValue(prefs)],
        child: const ThemeGalleryScreen(),
      ),
    );
    await settleShot(tester);

    expect(find.text('DARK'), findsOneWidget);
    await maybeWriteShot(tester, find.byKey(key), 'shot-themes.png');
  });
}

/// The app the shots are taken inside — a real `MaterialApp` wearing the real
/// theme, rebuilt from the theme and preset controllers exactly as
/// `ManhwaManiacsApp` wires them, wrapped in the boundary the capture reads.
Widget _shotApp({
  required GlobalKey key,
  required List<Override> overrides,
  required Widget child,
}) {
  return RepaintBoundary(
    key: key,
    child: ProviderScope(
      overrides: [
        apiBaseUrlOverride(shotBaseUrl),
        authenticatedAuthOverride(),
        activeProfileOverride(),
        profileSessionReadyOverride(),
        ...overrides,
      ],
      child: Consumer(
        builder: (context, ref, _) => MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: AppTheme.fromPalette(
            ref.watch(themeControllerProvider),
            metrics: ref.watch(presetControllerProvider),
          ),
          home: child,
        ),
      ),
    ),
  );
}

/// The one source the fixture library is followed from.
///
/// Stubbed even in manga mode: with the novels gate open, `ContentModeScope`
/// builds its manga/novel index from a real `/sources` call otherwise, and a
/// follow row carries a source id but no kind — so this listing is what makes
/// the novel fixtures novels.
Override _shelfSource({required bool novels}) =>
    sourcesListProvider.overrideWith(
      (ref) async => [
        SourceSummary(
          id: 'shelf',
          name: 'Shelf',
          description: '',
          browsable: true,
          supportsImport: false,
          contentKind: novels ? kNovelContentKind : kMangaContentKind,
        ),
      ],
    );

Override _followedOverride(List<ShotSeries> series) =>
    updatesProvider.overrideWith(
      () => _StaticUpdates(
        UpdatesState(
          notifications: const <UpdateNotification>[],
          unreadCount: 0,
          followed: shotFollowed(series),
        ),
      ),
    );

/// Paints the fixture covers and registers them with the suite's cover server.
Future<void> paintCovers(WidgetTester tester, List<ShotSeries> series) async {
  final covers = <String, Uint8List>{};
  await tester.runAsync(() async {
    for (var i = 0; i < series.length; i++) {
      covers[shotCoverPath(series[i])] =
          await ShotCoverArt(title: series[i].title, seed: i).toPng();
    }
  });
  addShotCovers(covers);
}

Future<SharedPreferences> shotPrefs() async {
  SharedPreferences.setMockInitialValues(testPrefsDefaults());
  return SharedPreferences.getInstance();
}

class _StaticUpdates extends UpdatesNotifier {
  _StaticUpdates(this.value);
  final UpdatesState value;
  @override
  Future<UpdatesState> build() async => value;
}

/// A believable, entirely invented reading record.
LibraryStatistics shotStatistics() {
  final today = DateTime(2026, 9, 4);
  return LibraryStatistics(
    followedTotal: 9,
    favorites: 3,
    byReadingStatus: const {
      'reading': 6,
      'completed': 2,
      'plan_to_read': 1,
    },
    chaptersCompleted: 1462,
    totals: ReadingTotals(
      sessions: 318,
      pagesRead: 21460,
      chaptersRead: 1462,
      seriesRead: 9,
      secondsRead: 486000,
      firstSessionAt: DateTime.utc(2026, 1, 12, 21),
      lastSessionAt: DateTime.utc(2026, 9, 4, 23, 40),
    ),
    window: const ReadingTotals(
      sessions: 41,
      pagesRead: 2870,
      chaptersRead: 163,
      seriesRead: 5,
      secondsRead: 61200,
    ),
    streak: ReadingStreak(
      currentDays: 12,
      longestDays: 31,
      lastActiveDate: today,
    ),
    daily: [
      for (var i = 29; i >= 0; i--)
        DailyActivity(
          date: today.subtract(Duration(days: i)),
          sessions: _dailyShape[i % _dailyShape.length],
          pagesRead: _dailyShape[i % _dailyShape.length] * 62,
          chaptersRead: _dailyShape[i % _dailyShape.length] * 4,
          secondsRead: _dailyShape[i % _dailyShape.length] * 1450,
        ),
    ],
    byHour: [
      for (var h = 0; h < 24; h++)
        HourActivity(
          hour: h,
          sessions: _hourShape[h],
          pagesRead: _hourShape[h] * 58,
          secondsRead: _hourShape[h] * 1320,
        ),
    ],
    bySource: const [
      SourceActivity(
        sourceId: 'shelf',
        name: 'Shelf',
        sessions: 41,
        pagesRead: 2870,
        chaptersRead: 163,
        seriesRead: 5,
        secondsRead: 61200,
      ),
    ],
    bySeries: [
      for (var i = 0; i < 4; i++)
        SeriesActivity(
          sourceId: 'shelf',
          seriesKey: shotManga[i].slug,
          title: shotManga[i].title,
          lastReadAt: DateTime.utc(2026, 9, 4, 23 - i),
          sessions: 42 - i * 9,
          pagesRead: 1180 - i * 210,
          chaptersRead: 74 - i * 13,
          secondsRead: 26400 - i * 4800,
        ),
    ],
    recentSessions: [
      for (var i = 0; i < 3; i++)
        RecentSession(
          sourceId: 'shelf',
          seriesKey: shotManga[i].slug,
          chapterKey: 'ch-${120 - i * 7}',
          chapterNumber: (120 - i * 7).toDouble(),
          title: shotManga[i].title,
          pagesRead: 48 - i * 6,
          secondsRead: 1500 - i * 220,
          startedAt: DateTime.utc(2026, 9, 4, 22 - i * 2),
          endedAt: DateTime.utc(2026, 9, 4, 22 - i * 2, 25),
        ),
    ],
  );
}

const _dailyShape = [3, 5, 2, 6, 4, 1, 7, 5, 3, 8, 4, 2, 6, 5, 9, 3, 4, 7, 2, 5, 6, 3, 8, 4, 5, 2, 7, 6, 3, 5];
const _hourShape = [2, 1, 0, 0, 0, 0, 0, 1, 3, 4, 2, 3, 5, 4, 3, 6, 5, 7, 9, 12, 15, 18, 22, 14];
