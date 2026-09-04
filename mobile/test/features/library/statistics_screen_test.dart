import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/screens/statistics_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// A dense 30-day window with reading on the last [activeDays] days — the
/// shape the backend actually sends (days off are zeros, never gaps).
List<DailyActivity> _denseDaily({required int activeDays}) {
  final today = DateTime(2026, 9, 4);
  return [
    for (var i = 29; i >= 0; i--)
      DailyActivity(
        date: today.subtract(Duration(days: i)),
        sessions: i < activeDays ? 1 : 0,
        pagesRead: i < activeDays ? 20 : 0,
        chaptersRead: i < activeDays ? 1 : 0,
        secondsRead: i < activeDays ? 600 : 0,
      ),
  ];
}

LibraryStatistics _richStats() => LibraryStatistics(
      followedTotal: 12,
      favorites: 3,
      byReadingStatus: const {'reading': 8, 'completed': 4},
      chaptersCompleted: 210,
      totals: ReadingTotals(
        sessions: 40,
        pagesRead: 1200,
        chaptersRead: 60,
        seriesRead: 5,
        secondsRead: 15120,
        firstSessionAt: DateTime.utc(2026, 8, 1, 10),
        lastSessionAt: DateTime.utc(2026, 9, 3, 18, 30),
      ),
      window: const ReadingTotals(
        sessions: 6,
        pagesRead: 180,
        chaptersRead: 9,
        seriesRead: 2,
        secondsRead: 5400,
      ),
      streak: ReadingStreak(
        currentDays: 3,
        longestDays: 7,
        lastActiveDate: DateTime(2026, 9, 4),
      ),
      daily: _denseDaily(activeDays: 3),
      byHour: [
        for (var h = 0; h < 24; h++)
          HourActivity(
            hour: h,
            sessions: h == 23 ? 4 : 0,
            pagesRead: h == 23 ? 120 : 0,
            secondsRead: h == 23 ? 3600 : 0,
          ),
      ],
      bySource: const [
        SourceActivity(
          sourceId: 'asurascans',
          name: 'Asura Scans',
          sessions: 6,
          pagesRead: 180,
          chaptersRead: 9,
          seriesRead: 2,
          secondsRead: 5400,
        ),
      ],
      bySeries: [
        SeriesActivity(
          sourceId: 'asurascans',
          seriesKey: 'solo-leveling',
          title: 'Solo Leveling',
          lastReadAt: DateTime.utc(2026, 9, 3, 18, 30),
          sessions: 4,
          pagesRead: 120,
          chaptersRead: 6,
          secondsRead: 3600,
        ),
      ],
      recentSessions: [
        RecentSession(
          sourceId: 'asurascans',
          seriesKey: 'solo-leveling',
          chapterKey: 'ch-110',
          chapterNumber: 110,
          title: 'Solo Leveling',
          pagesRead: 30,
          secondsRead: 900,
          startedAt: DateTime.utc(2026, 9, 3, 18),
          endedAt: DateTime.utc(2026, 9, 3, 18, 15),
        ),
      ],
    );

/// One recorded session ever — what the owner's profile looks like on day one
/// of session recording. Everything must render without NaN or div-by-zero.
LibraryStatistics _singleSessionStats() => LibraryStatistics(
      followedTotal: 12,
      favorites: 3,
      byReadingStatus: const {'reading': 8},
      chaptersCompleted: 210,
      totals: const ReadingTotals(
        sessions: 1,
        pagesRead: 14,
        chaptersRead: 1,
        seriesRead: 1,
        // secondsRead stays 0 (no elapsed time reported) — the totals grid
        // must fall back to the session count instead of a permanent "0m".
      ),
      window: const ReadingTotals(sessions: 1, pagesRead: 14, chaptersRead: 1, seriesRead: 1),
      streak: ReadingStreak(currentDays: 1, longestDays: 1, lastActiveDate: DateTime(2026, 9, 4)),
      daily: _denseDaily(activeDays: 1),
      byHour: [
        for (var h = 0; h < 24; h++)
          HourActivity(hour: h, sessions: h == 22 ? 1 : 0, pagesRead: h == 22 ? 14 : 0),
      ],
      bySource: const [
        SourceActivity(sourceId: 'asurascans', name: 'Asura Scans', sessions: 1, pagesRead: 14),
      ],
    );

Future<Widget> _wrap(Override statsOverride) async {
  // SeriesCoverImage (Most Read rows) resolves the active profile, which
  // reads shared prefs — the same seeding remaining_screens_test.dart uses.
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  return ProviderScope(
    overrides: [
      apiBaseUrlOverride('http://127.0.0.1:8000'),
      sharedPrefsProvider.overrideWithValue(prefs),
      statsOverride,
    ],
    child: const MaterialApp(home: StatisticsScreen()),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('StatisticsScreen with reading history', () {
    testWidgets('renders streak, activity, totals and breakdowns', (tester) async {
      // The screen is a lazy ListView far taller than the default 600px
      // surface; a tall surface builds every section in one layout pass.
      await tester.binding.setSurfaceSize(const Size(700, 3400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        await _wrap(statisticsProvider.overrideWith((ref) async => _richStats())),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      // The empty state must not appear for a profile with sessions.
      expect(find.text('No reading recorded yet'), findsNothing);

      // Streak.
      expect(find.text('Current streak'), findsOneWidget);
      expect(find.text('3'), findsWidgets);
      expect(find.text('Longest'), findsOneWidget);

      // Activity window summary line.
      expect(find.text('Activity'), findsOneWidget);
      expect(find.textContaining('in the last 30 days'), findsOneWidget);

      // All-time totals, with humane duration (15120s → 4h 12m, never raw).
      expect(find.text('Chapters Read'), findsOneWidget);
      expect(find.text('4h 12m'), findsOneWidget);
      expect(find.text('15120'), findsNothing);

      // Breakdowns and lists.
      expect(find.text('Asura Scans'), findsOneWidget);
      expect(find.text('Solo Leveling'), findsWidgets);

      // Library shape still present below.
      expect(find.text('Followed Series'), findsOneWidget);
    });

    testWidgets('a single session renders without NaN or empty-state lies',
        (tester) async {
      await tester.binding.setSurfaceSize(const Size(700, 3400));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        await _wrap(statisticsProvider.overrideWith((ref) async => _singleSessionStats())),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('No reading recorded yet'), findsNothing);
      expect(find.text('Current streak'), findsOneWidget);
      // No elapsed time reported → sessions card, not a permanent "0m".
      expect(find.text('Sessions'), findsOneWidget);
      expect(find.text('0m'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('StatisticsScreen error state', () {
    testWidgets('failure shows message and retry refetches', (tester) async {
      var calls = 0;
      await tester.pumpWidget(
        await _wrap(
          statisticsProvider.overrideWith((ref) async {
            calls++;
            if (calls == 1) {
              throw const UnknownError(message: 'boom');
            }
            return _singleSessionStats();
          }),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(calls, 2);
      expect(find.text('Retry'), findsNothing);
      expect(find.text('Current streak'), findsOneWidget);
    });
  });
}
