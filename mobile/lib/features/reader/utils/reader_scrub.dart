/// Geometry for the bottom bar's chapter scrubber.
///
/// Ported from the web reader (`frontend/src/features/reader/scrub.ts`) so both
/// clients mean the same thing by the handle's position: it sits at the very
/// start of the rail on page 1 and at the very end on the last page. A rail that
/// mapped page N to N/total could never reach the final page.
///
/// The rail itself is a real [Slider] running 1..pageCount, so the ratio maths
/// the web has to do by hand falls out of the widget; what is left is the
/// clamping, which is where an off-by-one would silently make the last page
/// unreachable again.
library;

/// Upper bound for the scrub slider.
///
/// A one-page chapter still needs `min < max` or the slider divides by zero
/// working out where to draw the handle, so it gets a nominal range and is left
/// disabled by [readerScrubEnabled].
double readerScrubMax(int pageCount) => pageCount > 1 ? pageCount.toDouble() : 2;

/// One stop per page, so dragging snaps to whole pages rather than landing
/// between two of them. ``null`` (continuous) for a chapter with nothing to
/// scrub through.
int? readerScrubDivisions(int pageCount) =>
    pageCount > 1 ? pageCount - 1 : null;

/// There is nowhere to scrub to in a chapter of one page.
bool readerScrubEnabled(int pageCount) => pageCount > 1;

/// Value the slider should show for [page].
///
/// Clamped because the page the reader reports back is measured from the scroll
/// offset and can lag a jump by a frame — an out-of-range value would assert.
double readerScrubValue(int page, int pageCount) {
  if (pageCount <= 0) return 1;
  return page.clamp(1, pageCount).toDouble();
}

/// Page a slider [value] means. Rounds to a whole page and clamps into the
/// chapter, so a drag to either end of the rail reaches the first/last page
/// exactly rather than stopping one short.
int readerScrubPage(double value, int pageCount) {
  if (pageCount <= 0 || !value.isFinite) return 1;
  return value.round().clamp(1, pageCount);
}
