import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_date.dart';

/// Noon on 2026-09-09, in the zone the test process happens to run in.
///
/// Every case below is built from LOCAL constructors rather than `DateTime.utc`
/// on purpose: the label is about the reader's calendar, so a test that pins
/// instants in UTC would assert a different answer in IST than in UTC and the
/// suite would pass or fail by where it ran. Local-to-local comparisons hold in
/// every zone.
final DateTime now = DateTime(2026, 9, 9, 12);

/// The same instant the backend would serialise for [local], as a naive string
/// with no timezone designator — which is what SQLite columns actually emit.
String naiveUtc(DateTime local) {
  final u = local.toUtc();
  String two(int v) => v.toString().padLeft(2, '0');
  return '${u.year}-${two(u.month)}-${two(u.day)}'
      'T${two(u.hour)}:${two(u.minute)}:${two(u.second)}';
}

void main() {
  group('chapterDateLabel', () {
    test('says nothing when the source published no date', () {
      expect(chapterDateLabel(null, now: now), isNull);
      expect(chapterDateLabel('', now: now), isNull);
      expect(chapterDateLabel('   ', now: now), isNull);
    });

    test('counts recent chapters in days, which is what a reader checks', () {
      expect(chapterDateLabel(naiveUtc(DateTime(2026, 9, 9, 9)), now: now), 'Today');
      expect(
        chapterDateLabel(naiveUtc(DateTime(2026, 9, 8, 9)), now: now),
        'Yesterday',
      );
      expect(chapterDateLabel(naiveUtc(DateTime(2026, 9, 6, 9)), now: now), '3d ago');
    });

    test('switches to a date once the age stops meaning anything', () {
      final label = chapterDateLabel(naiveUtc(DateTime(2026, 7, 28, 9)), now: now);

      expect(label, isNot(contains('ago')));
      expect(label, contains('2026'));
    });

    test('counts by calendar day, not by elapsed hours', () {
      // Posted at 23:00 last night: two hours old, but it is Yesterday's
      // chapter and a reader scanning the list reads it that way.
      expect(
        chapterDateLabel(
          naiveUtc(DateTime(2026, 9, 8, 23)),
          now: DateTime(2026, 9, 9, 1),
        ),
        'Yesterday',
      );
    });

    test('reads a naive server timestamp as UTC, not as local time', () {
      // The backend serialises UTC out of a naive SQLite DATETIME, so the same
      // instant reaches us both with and without a Z depending on the path.
      // Both must land on the same day — this is the bug core/time/
      // server_instant.dart exists to prevent, and the models used to bypass it
      // with a bare DateTime.tryParse.
      final instant = DateTime(2026, 9, 8, 9).toUtc();

      expect(
        chapterDateLabel(naiveUtc(DateTime(2026, 9, 8, 9)), now: now),
        chapterDateLabel(instant.toIso8601String(), now: now),
      );
      expect(chapterDateLabel(naiveUtc(DateTime(2026, 9, 8, 9)), now: now), 'Yesterday');
    });

    test('handles a bare calendar date, which is most of what sources publish', () {
      expect(chapterDateLabel('2026-09-08', now: DateTime.utc(2026, 9, 9, 12)), 'Yesterday');
    });

    test('passes a scraped string through rather than swallowing it', () {
      // These four shapes are asserted in the backend's own connector tests.
      // Parsing used to return null for every one of them, so the tile showed
      // no date at all while the web showed the source's own wording.
      expect(chapterDateLabel('18 Mar 2021', now: now), '18 Mar 2021');
      expect(chapterDateLabel('Apr 22,2016', now: now), 'Apr 22,2016');
      expect(chapterDateLabel('Nov 05,2018', now: now), 'Nov 05,2018');
      expect(chapterDateLabel('2019/07/13', now: now), '2019/07/13');
      expect(chapterDateLabel('2 days ago', now: now), '2 days ago');
    });

    test('does not promise a future a reader cannot act on', () {
      expect(
        chapterDateLabel(naiveUtc(DateTime(2026, 9, 11)), now: now),
        'Just now',
      );
    });

    test('agrees with the website for every step of the scale', () {
      // The web helper (frontend/src/features/sources/chapter-date.ts) uses
      // these exact words and the same calendar-day rule; a chapter must not
      // read differently on the two clients.
      final cases = <DateTime, String>{
        DateTime(2026, 9, 9, 8): 'Today',
        DateTime(2026, 9, 8, 8): 'Yesterday',
        DateTime(2026, 9, 7, 8): '2d ago',
        DateTime(2026, 9, 4, 8): '5d ago',
      };

      cases.forEach((at, expected) {
        expect(chapterDateLabel(naiveUtc(at), now: now), expected, reason: '$at');
      });
    });
  });
}
