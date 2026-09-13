import 'package:manhwamaniacs/core/time/server_instant.dart';

/// When a chapter went up, as a chapter row should say it.
///
/// Recent chapters get a relative age, because "2d ago" is the thing a reader
/// checking for new chapters actually wants to know. Past a week the relative
/// form stops carrying information ("43d ago") and it becomes a date.
///
/// Takes the source's RAW string rather than a parsed `DateTime`, because the
/// sources are not consistent and the parse is where the information was being
/// lost. A connector publishes whatever its site publishes: an ISO instant, a
/// naive `YYYY-MM-DDTHH:MM:SS` with no designator, a bare `YYYY-MM-DD`, or a
/// string that was never a date at all. Anything unparseable is passed through
/// UNCHANGED, because those strings are already the sentence the site showed a
/// human — "18 Mar 2021" (manhwa18), "Apr 22,2016" (mangatown),
/// "Nov 05,2018" (fanfox), "2019/07/13" (mangafreak). Dropping them showed the
/// reader nothing while the source had told us something.
///
/// Mirrors the website's `features/sources/chapter-date.ts` so the same chapter
/// reads the same on both clients — including the day rule below, which the two
/// did not actually agree on before.
String? chapterDateLabel(String? uploaded, {DateTime? now}) {
  final raw = uploaded?.trim();
  if (raw == null || raw.isEmpty) return null;

  // Only the shapes the backend emits count as a date; everything else is the
  // source's own wording and is passed through. The gate is explicit rather
  // than "whatever the platform can parse", because the platforms disagree and
  // that is how the two clients drifted: Date.parse("Apr 22,2016") succeeds in
  // V8 and reformats it, while DateTime.tryParse returns null and this row
  // rendered nothing at all.
  if (!_backendDate.hasMatch(raw)) return raw;

  // serverInstant supplies the missing UTC designator. Without it
  // DateTime.tryParse reads an offset-less server timestamp as LOCAL and
  // shifts it by the device's offset, which in +05:30 is enough to move a
  // chapter to the wrong day.
  final at = serverInstant(raw);
  if (at == null) return raw;

  final days = _calendarDaysBetween(at, now ?? DateTime.now());

  // A source's clock can sit ahead of ours, and a scheduled chapter is a real
  // thing. Neither is worth an "in 3 days" the reader cannot act on.
  if (days < 0) return 'Just now';
  if (days == 0) return 'Today';
  if (days == 1) return 'Yesterday';
  if (days < 7) return '${days}d ago';

  final local = at.toLocal();
  return '${_months[local.month - 1]} ${local.day}, ${local.year}';
}

/// Calendar days between two instants, counted in the READER'S OWN zone.
///
/// Two decisions, both of which the two clients previously got differently:
///
/// 1. By date, not by elapsed hours. A chapter posted at 23:00 last night is
///    "Yesterday", not "Today", even though it is only two hours old — that is
///    how someone scanning a list of dates reads it.
/// 2. In local time, not UTC. "Yesterday" has to mean the day before the
///    reader's today. Counting UTC days labels a chapter posted 23:00 UTC as
///    "Yesterday" for a reader in +05:30 for whom it arrived at 04:30 *this*
///    morning.
int _calendarDaysBetween(DateTime at, DateTime reference) {
  final a = at.toLocal();
  final b = reference.toLocal();
  // Build both midnights as UTC so the subtraction cannot be distorted by a
  // DST transition falling between them; only the y/m/d taken from local time
  // matters here.
  return DateTime.utc(b.year, b.month, b.day)
      .difference(DateTime.utc(a.year, a.month, a.day))
      .inDays;
}

/// Kept identical to `BACKEND_DATE` in the web helper.
final RegExp _backendDate = RegExp(
  r'^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:?\d{2})?)?$',
);

const List<String> _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];
