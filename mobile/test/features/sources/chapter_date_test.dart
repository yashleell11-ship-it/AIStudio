import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_date.dart';

/// 2026-09-09 12:00 UTC.
final DateTime now = DateTime.utc(2026, 9, 9, 12);

void main() {
  group('chapterDateLabel', () {
    test('says nothing when the source published no date', () {
      expect(chapterDateLabel(null, now: now), isNull);
    });

    test('counts recent chapters in days, which is what a reader checks', () {
      expect(chapterDateLabel(DateTime.utc(2026, 9, 9, 9), now: now), 'Today');
      expect(
        chapterDateLabel(DateTime.utc(2026, 9, 8, 9), now: now),
        'Yesterday',
      );
      expect(chapterDateLabel(DateTime.utc(2026, 9, 6, 9), now: now), '3d ago');
    });

    test('switches to a date once the age stops meaning anything', () {
      final label = chapterDateLabel(DateTime.utc(2026, 7, 28, 9), now: now);

      expect(label, isNot(contains('ago')));
      expect(label, contains('2026'));
    });

    test('counts by calendar day, not by elapsed hours', () {
      // Posted at 23:00 last night: two hours old, but it is Yesterday's
      // chapter and a reader scanning the list reads it that way.
      expect(
        chapterDateLabel(DateTime.utc(2026, 9, 8, 23), now: DateTime.utc(2026, 9, 9, 1)),
        'Yesterday',
      );
    });

    test('does not promise a future a reader cannot act on', () {
      expect(
        chapterDateLabel(DateTime.utc(2026, 9, 11), now: now),
        'Just now',
      );
    });

    test('reads a local-zone timestamp as the same instant', () {
      final utc = DateTime.utc(2026, 9, 8, 9);

      expect(chapterDateLabel(utc.toLocal(), now: now), 'Yesterday');
    });

    test('agrees with the website for every step of the scale', () {
      // The web helper (features/sources/chapter-date.ts) uses these exact
      // words; a chapter must not read differently on the two clients.
      final cases = <DateTime, String>{
        DateTime.utc(2026, 9, 9): 'Today',
        DateTime.utc(2026, 9, 8): 'Yesterday',
        DateTime.utc(2026, 9, 7): '2d ago',
        DateTime.utc(2026, 9, 4): '5d ago',
      };

      cases.forEach((at, expected) {
        expect(chapterDateLabel(at, now: now), expected, reason: '$at');
      });
    });
  });
}
