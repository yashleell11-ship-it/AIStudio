import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/reader/utils/reading_clock.dart';

void main() {
  final start = DateTime.utc(2026, 9, 5, 20);

  group('ReadingClock', () {
    test('reports the delta since the last push, never a running total', () {
      final clock = ReadingClock(start);

      expect(clock.elapsed(start.add(const Duration(seconds: 30))), 30);
      // The server ADDS what it is sent, so the second push must report 45,
      // not 75 — a cumulative figure would inflate the statistic every time.
      expect(clock.elapsed(start.add(const Duration(seconds: 75))), 45);
    });

    test('sub-second remainders carry instead of truncating to nothing', () {
      final clock = ReadingClock(start);

      // Pages settle every 500ms; truncating each call would report 0 forever.
      expect(clock.elapsed(start.add(const Duration(milliseconds: 1500))), 1);
      expect(clock.elapsed(start.add(const Duration(milliseconds: 3000))), 2);
    });

    test('a reader left open all night credits the cap, not the night', () {
      final clock = ReadingClock(start);

      expect(
        clock.elapsed(start.add(const Duration(hours: 9))),
        kMaxReadingGapSeconds,
      );
      // And the skipped hours are not banked for the next push.
      expect(
        clock.elapsed(start.add(const Duration(hours: 9, seconds: 20))),
        20,
      );
    });

    test('a device clock that jumps backwards credits nothing', () {
      final clock = ReadingClock(start);

      expect(clock.elapsed(start.subtract(const Duration(minutes: 5))), 0);
      // Re-anchored at the new "now" rather than owing five minutes.
      expect(
        clock.elapsed(start.subtract(const Duration(minutes: 4))),
        60,
      );
    });
  });
}
