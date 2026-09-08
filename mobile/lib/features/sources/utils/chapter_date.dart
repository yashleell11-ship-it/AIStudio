/// When a chapter went up, as a chapter row should say it.
///
/// Recent chapters get a relative age, because "2d ago" is the thing a reader
/// checking for new chapters actually wants to know. Past a week the relative
/// form stops carrying information ("43d ago") and it becomes a date.
///
/// Mirrors the website's `features/sources/chapter-date.ts` so the same chapter
/// reads the same on both clients.
String? chapterDateLabel(DateTime? uploaded, {DateTime? now}) {
  if (uploaded == null) return null;
  final at = uploaded.toUtc();
  final reference = (now ?? DateTime.now()).toUtc();

  final days = _wholeDaysBetween(at, reference);

  // A source's clock can sit ahead of ours, and a scheduled chapter is a real
  // thing. Neither is worth an "in 3 days" the reader cannot act on.
  if (days < 0) return 'Just now';
  if (days == 0) return 'Today';
  if (days == 1) return 'Yesterday';
  if (days < 7) return '${days}d ago';

  final local = uploaded.toLocal();
  return '${_months[local.month - 1]} ${local.day}, ${local.year}';
}

/// Calendar days between two instants, counted by date rather than by elapsed
/// hours: a chapter posted at 23:00 yesterday is "Yesterday", not "Today",
/// even though it is only two hours old.
int _wholeDaysBetween(DateTime at, DateTime reference) {
  final a = DateTime.utc(at.year, at.month, at.day);
  final b = DateTime.utc(reference.year, reference.month, reference.day);
  return b.difference(a).inDays;
}

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
