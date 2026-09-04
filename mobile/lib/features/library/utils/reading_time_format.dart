import 'package:intl/intl.dart';

/// Display helpers for the reading-time numbers in `GET /library/statistics`.
///
/// The API reports durations in seconds and instants in UTC. Neither is
/// readable as-is: "15120" is not a length of time anybody recognises, and a
/// raw timestamp on a "recent activity" row makes the reader do date
/// arithmetic to answer "was that today?".

/// A reading duration, e.g. `4h 12m`, `12m`, `45s`.
///
/// Minutes are dropped from a whole-hour total ("4h", not "4h 0m") and hours
/// keep counting past a day: "38h" is a reading total, and no one thinks of
/// their year in book-days.
String formatReadingDuration(int seconds) {
  if (seconds <= 0) return '0m';
  if (seconds < 60) return '${seconds}s';
  final minutes = seconds ~/ 60;
  if (minutes < 60) return '${minutes}m';
  final hours = minutes ~/ 60;
  final remainder = minutes % 60;
  return remainder == 0 ? '${hours}h' : '${hours}h ${remainder}m';
}

/// How long ago [when] was, in the coarsest useful unit.
///
/// Falls back to an absolute date past a week — "23d ago" is a number to
/// decode, "12 Aug 2026" is a date. [now] is injectable so callers (and tests)
/// can pin the reference instant.
String formatTimeAgo(DateTime when, {DateTime? now}) {
  final local = when.toLocal();
  final delta = (now ?? DateTime.now()).difference(local);
  if (delta.inMinutes < 1) return 'Just now';
  if (delta.inMinutes < 60) return '${delta.inMinutes}m ago';
  if (delta.inHours < 24) return '${delta.inHours}h ago';
  if (delta.inDays < 7) return '${delta.inDays}d ago';
  return DateFormat.yMMMd().format(local);
}

/// A calendar day for an axis label or a streak line, e.g. `Sep 3`.
String formatShortDay(DateTime day) => DateFormat.MMMd().format(day);

/// An hour of the day for the reading-clock labels, e.g. `11 PM` — locale
/// aware, so a 24-hour locale gets `23`.
String formatHourOfDay(int hour) =>
    DateFormat.j().format(DateTime(2000, 1, 1, hour.clamp(0, 23)));

/// `1 page` / `12 pages` — the count is almost always plural, but a
/// near-empty profile is exactly where the singular shows up.
String formatPages(int pages) => pages == 1 ? '1 page' : '$pages pages';

/// `1 chapter` / `12 chapters`.
String formatChapters(int chapters) =>
    chapters == 1 ? '1 chapter' : '$chapters chapters';
