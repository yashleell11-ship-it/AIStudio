import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';

void main() {
  group('LibraryStatistics.fromJson', () {
    test('parses followed-series stat fields from API response', () {
      final stats = LibraryStatistics.fromJson({
        'followed_total': 42,
        'favorites': 5,
        'by_reading_status': {'reading': 8, 'completed': 10, 'unread': 24},
        'chapters_completed': 1240,
      });

      expect(stats.followedTotal, 42);
      expect(stats.favorites, 5);
      expect(stats.byReadingStatus['completed'], 10);
      expect(stats.chaptersCompleted, 1240);
    });

    test('defaults missing fields to empty/zero', () {
      final stats = LibraryStatistics.fromJson(const {});

      expect(stats.followedTotal, 0);
      expect(stats.favorites, 0);
      expect(stats.byReadingStatus, isEmpty);
      expect(stats.chaptersCompleted, 0);
      expect(stats.rangeDays, 30);
      expect(stats.totals.sessions, 0);
      expect(stats.window.sessions, 0);
      expect(stats.streak.currentDays, 0);
      expect(stats.daily, isEmpty);
      expect(stats.byHour, isEmpty);
      expect(stats.bySource, isEmpty);
      expect(stats.bySeries, isEmpty);
      expect(stats.recentSessions, isEmpty);
      expect(stats.hasReadingHistory, isFalse);
      expect(stats.hasWindowActivity, isFalse);
    });

    test('parses the session-derived payload end to end', () {
      final stats = LibraryStatistics.fromJson({
        'followed_total': 3,
        'favorites': 1,
        'by_reading_status': {'reading': 3},
        'chapters_completed': 20,
        'range': {
          'days': 30,
          'timezone_offset_minutes': 330,
          'session_cap_seconds': 3600,
        },
        'totals': {
          'sessions': 12,
          'pages_read': 340,
          'chapters_read': 18,
          'series_read': 3,
          'seconds_read': 15120,
          'first_session_at': '2026-08-01T10:00:00',
          'last_session_at': '2026-09-03T18:30:00',
        },
        'window': {
          'sessions': 4,
          'pages_read': 120,
          'chapters_read': 6,
          'series_read': 2,
          'seconds_read': 5000,
        },
        'streak': {
          'current_days': 2,
          'longest_days': 5,
          'last_active_date': '2026-09-03',
        },
        'daily': [
          {'date': '2026-09-02', 'sessions': 0, 'pages_read': 0},
          {'date': '2026-09-03', 'sessions': 2, 'pages_read': 60, 'chapters_read': 3, 'seconds_read': 2400},
        ],
        'by_hour': [
          {'hour': 23, 'sessions': 2, 'pages_read': 60, 'seconds_read': 2400},
        ],
        'by_source': [
          {
            'source_id': 'asurascans',
            'name': 'Asura Scans',
            'sessions': 4,
            'pages_read': 120,
            'chapters_read': 6,
            'series_read': 2,
            'seconds_read': 5000,
          },
        ],
        'by_series': [
          {
            'source_id': 'asurascans',
            'series_key': 'solo-leveling',
            'title': 'Solo Leveling',
            'last_read_at': '2026-09-03T18:30:00',
            'sessions': 3,
            'pages_read': 90,
            'chapters_read': 4,
            'seconds_read': 3600,
          },
        ],
        'recent_sessions': [
          {
            'source_id': 'asurascans',
            'series_key': 'solo-leveling',
            'chapter_key': 'ch-110',
            'chapter_number': 110,
            'title': 'Solo Leveling',
            'pages_read': 30,
            'seconds_read': 900,
            'started_at': '2026-09-03T18:00:00',
            'ended_at': '2026-09-03T18:15:00',
          },
        ],
      });

      expect(stats.hasReadingHistory, isTrue);
      expect(stats.hasWindowActivity, isTrue);
      expect(stats.rangeDays, 30);

      expect(stats.totals.sessions, 12);
      expect(stats.totals.pagesRead, 340);
      expect(stats.totals.chaptersRead, 18);
      expect(stats.totals.seriesRead, 3);
      expect(stats.totals.secondsRead, 15120);
      expect(stats.window.sessions, 4);

      expect(stats.streak.currentDays, 2);
      expect(stats.streak.longestDays, 5);

      expect(stats.daily, hasLength(2));
      expect(stats.daily.first.sessions, 0);
      expect(stats.daily.last.pagesRead, 60);
      expect(stats.byHour.single.hour, 23);
      expect(stats.bySource.single.name, 'Asura Scans');
      expect(stats.bySeries.single.title, 'Solo Leveling');
      expect(stats.recentSessions.single.chapterNumber, 110);
      expect(stats.recentSessions.single.pagesRead, 30);
    });

    test('reads naive backend timestamps as UTC instants', () {
      // Every timestamp column on the backend is naive SQLite DATETIME holding
      // UTC; DateTime.parse would read the offset-less string as *local* and
      // shift every "3h ago" by the device's UTC offset.
      final stats = LibraryStatistics.fromJson({
        'totals': {'sessions': 1, 'first_session_at': '2026-09-01T10:00:00'},
      });

      final first = stats.totals.firstSessionAt;
      expect(first, isNotNull);
      expect(first!.isUtc, isTrue);
      expect(first, DateTime.utc(2026, 9, 1, 10));
    });

    test('keeps an already-zoned timestamp as sent', () {
      final stats = LibraryStatistics.fromJson({
        'totals': {'sessions': 1, 'last_session_at': '2026-09-01T10:00:00Z'},
      });

      expect(stats.totals.lastSessionAt, DateTime.utc(2026, 9, 1, 10));
    });

    test('parses day buckets as local calendar dates, not instants', () {
      // `daily[].date` and `streak.last_active_date` are already bucketed at
      // the offset the client sent — shifting them into UTC would relabel the
      // chart's axis by a day for any non-UTC reader.
      final stats = LibraryStatistics.fromJson({
        'streak': {'current_days': 1, 'longest_days': 1, 'last_active_date': '2026-09-03'},
        'daily': [
          {'date': '2026-09-03', 'sessions': 1},
        ],
      });

      expect(stats.streak.lastActiveDate!.isUtc, isFalse);
      expect(stats.streak.lastActiveDate, DateTime(2026, 9, 3));
      expect(stats.daily.single.date, DateTime(2026, 9, 3));
    });

    test('tolerates malformed list entries and timestamps', () {
      // One bad row must not blank the whole screen.
      final stats = LibraryStatistics.fromJson({
        'totals': {'sessions': 2, 'first_session_at': 'not-a-date'},
        'daily': [
          'garbage',
          {'date': '2026-09-03', 'sessions': 1},
          42,
        ],
        'by_source': 'not-a-list',
      });

      expect(stats.totals.firstSessionAt, isNull);
      expect(stats.daily, hasLength(1));
      expect(stats.bySource, isEmpty);
    });

    test('title for an unfollowed series stays null, not empty', () {
      final stats = LibraryStatistics.fromJson({
        'by_series': [
          {'source_id': 'asurascans', 'series_key': 'gone', 'title': null, 'sessions': 1},
        ],
      });

      expect(stats.bySeries.single.title, isNull);
    });
  });
}
