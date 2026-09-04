import 'package:manhwamaniacs/features/reader/utils/page_extents.dart';

/// Exactly where the reader is: a 1-based page and how far down that page.
///
/// The fraction is of the page's own extent, not of the viewport and not in
/// pixels. Pixels would be meaningless off this device — the same chapter is
/// laid out at a different width on a tablet and a different one again on the
/// web, and `chapter_progress.scroll_offset_px` is what that mistake looks
/// like once it has shipped.
typedef ReaderAnchor = ({int page, double fraction});

/// The anchor for a scroll offset.
///
/// Measured at the same probe point [ReaderPageMetrics.pageAtOffset] uses, and
/// that is the point: if "which page" were answered from the reading line and
/// "where in it" from the top of the viewport, the two could disagree — a
/// probe just into page 4 would report page 4 at a *negative* fraction. One
/// point, one answer.
ReaderAnchor anchorAtOffset(ReaderPageMetrics metrics, double scrollOffset) {
  if (metrics.pageCount == 0) return (page: 1, fraction: 0);
  final page = metrics.pageAtOffset(scrollOffset);
  final index = page - 1;
  final inset = metrics.leadingInsetAt(index);
  final start = metrics.offsetToPage(page) + inset;
  final extent = metrics.extentAt(index) - inset;
  if (extent <= 0) return (page: page, fraction: 0);
  final probe = scrollOffset + readerVisiblePageLead;
  return (
    page: page,
    fraction: ((probe - start) / extent).clamp(0.0, 1.0),
  );
}

/// The scroll offset that puts the reader back on [anchor] — the exact
/// inverse of [anchorAtOffset], so capturing a position and restoring it is a
/// round trip and not an approximation.
///
/// [anchor.page] is clamped into the pages that actually exist. That IS the
/// honest degradation the design asks for: a chapter that has lost pages
/// upstream lands the reader on its last page rather than failing to open or
/// silently dumping them at the top. Callers detect it with
/// [anchorPageIsMissing] and say so.
double offsetForAnchor(ReaderPageMetrics metrics, ReaderAnchor anchor) {
  if (metrics.pageCount == 0) return 0;
  final index = (anchor.page - 1).clamp(0, metrics.pageCount - 1);
  final inset = metrics.leadingInsetAt(index);
  final start = metrics.offsetToPage(index + 1) + inset;
  final extent = metrics.extentAt(index) - inset;
  final within = extent <= 0 ? 0.0 : anchor.fraction.clamp(0.0, 1.0) * extent;
  final offset = start + within - readerVisiblePageLead;
  return offset < 0 ? 0 : offset;
}

/// Whether a requested page is past the end of what the chapter now holds —
/// i.e. whether the restore is about to land somewhere other than where the
/// bookmark was made.
bool anchorPageIsMissing(int requestedPage, int pageCount) =>
    pageCount > 0 && requestedPage > pageCount;
