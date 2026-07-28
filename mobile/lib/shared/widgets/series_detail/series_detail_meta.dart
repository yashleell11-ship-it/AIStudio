import 'package:intl/intl.dart';

/// Separator between the summary line's facts. Wide enough to read as separate
/// statements at a glance rather than one run-on sentence.
const String _metaSeparator = '  ·  ';

/// Builds the one-line summary that sits under the series title on both series
/// pages, e.g. `Latest: Chapter 322  ·  322 chapters  ·  8,940 pages  ·  61% read`.
///
/// Every part is dropped when it is not actually known, so the line never
/// states a count of zero or a percentage the page cannot back up. Returns null
/// when nothing at all is known — callers then render no line rather than an
/// empty one.
///
/// [pageCount] and [readPct] are library-only facts (a source catalog knows
/// neither until a chapter is downloaded and read); passing them as 0/null on
/// the source page is what keeps one builder serving both.
String? seriesDetailMetaLine({
  String? latestChapterLabel,
  required int chapterCount,
  int pageCount = 0,
  double? readPct,
}) {
  final parts = <String>[];

  final latest = latestChapterLabel?.trim();
  if (latest != null && latest.isNotEmpty) parts.add('Latest: $latest');

  if (chapterCount > 0) {
    parts.add(chapterCount == 1 ? '1 chapter' : '$chapterCount chapters');
  }

  if (pageCount > 0) {
    final formatted = NumberFormat.decimalPattern().format(pageCount);
    parts.add(pageCount == 1 ? '1 page' : '$formatted pages');
  }

  // A 0% read series is still worth stating -- it is the answer "none of it" --
  // but only once there is progress to report at all, which is what a non-null
  // percentage means.
  if (readPct != null) parts.add('${readPct.round()}% read');

  return parts.isEmpty ? null : parts.join(_metaSeparator);
}

/// Per-chapter progress line. Unread → `20 pages`; part-read → `7/20 pages`;
/// finished → `20/20 pages`. Returns null when the page count is unknown, so a
/// source that omits page counts shows no line instead of "0 pages".
///
/// [page] is the last page reached; null means the chapter was never opened.
/// [completed] wins over [page] because a finished chapter should read
/// `20/20`, not `19/20`, whatever page the reader happened to stop on.
String? seriesChapterProgressText({
  required int pageCount,
  int? page,
  bool completed = false,
}) {
  if (pageCount <= 0) return null;
  if (completed) return '$pageCount/$pageCount pages';
  if (page == null) return '$pageCount pages';
  return '$page/$pageCount pages';
}
