import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/utils/reading_time_format.dart';

void main() {
  group('formatReadingDuration', () {
    test('never emits a raw seconds number for readable spans', () {
      expect(formatReadingDuration(15120), '4h 12m');
    });

    test('zero and negatives read as 0m', () {
      expect(formatReadingDuration(0), '0m');
      expect(formatReadingDuration(-5), '0m');
    });

    test('sub-minute spans keep seconds', () {
      expect(formatReadingDuration(45), '45s');
      expect(formatReadingDuration(59), '59s');
    });

    test('minutes below an hour', () {
      expect(formatReadingDuration(60), '1m');
      expect(formatReadingDuration(12 * 60 + 30), '12m');
      expect(formatReadingDuration(3599), '59m');
    });

    test('whole hours drop the zero-minute tail', () {
      expect(formatReadingDuration(3600), '1h');
      expect(formatReadingDuration(4 * 3600), '4h');
    });

    test('keeps counting hours past a day', () {
      expect(formatReadingDuration(38 * 3600), '38h');
    });
  });

  group('formatTimeAgo', () {
    final now = DateTime(2026, 9, 4, 12);

    test('under a minute is "Just now"', () {
      expect(formatTimeAgo(now.subtract(const Duration(seconds: 20)), now: now), 'Just now');
    });

    test('coarsest useful unit within a week', () {
      expect(formatTimeAgo(now.subtract(const Duration(minutes: 5)), now: now), '5m ago');
      expect(formatTimeAgo(now.subtract(const Duration(hours: 3)), now: now), '3h ago');
      expect(formatTimeAgo(now.subtract(const Duration(days: 2)), now: now), '2d ago');
    });

    test('falls back to an absolute date past a week', () {
      expect(
        formatTimeAgo(DateTime(2026, 8, 12, 9), now: now),
        'Aug 12, 2026',
      );
    });
  });

  group('count labels', () {
    test('pages pluralise except exactly one', () {
      expect(formatPages(0), '0 pages');
      expect(formatPages(1), '1 page');
      expect(formatPages(12), '12 pages');
    });

    test('chapters pluralise except exactly one', () {
      expect(formatChapters(1), '1 chapter');
      expect(formatChapters(3), '3 chapters');
    });
  });

  group('axis labels', () {
    test('formatShortDay is a compact month-day', () {
      expect(formatShortDay(DateTime(2026, 9, 3)), 'Sep 3');
    });

    test('formatHourOfDay clamps out-of-range hours instead of throwing', () {
      // The backend promises 0..23, but an axis label must not be the thing
      // that crashes the screen if that promise ever breaks.
      expect(formatHourOfDay(-1), formatHourOfDay(0));
      expect(formatHourOfDay(24), formatHourOfDay(23));
    });
  });
}
