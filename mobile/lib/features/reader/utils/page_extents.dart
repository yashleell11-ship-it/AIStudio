import 'dart:collection';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Space the page list reserves before the first page. A page's scroll offset
/// is measured from the top of the list, not from the top of the first page, so
/// the geometry here has to account for it or every page jump lands short.
const double readerListLeadingPadding = AppSpacing.lg;

/// Space after the last page so the bottom bar never covers it.
const double readerListTrailingPadding = 120;

/// Gap after each page in the paged (horizontal) reader. Vertical webtoon pages
/// butt up flush — any gap there reads as a seam mid-strip — so this applies to
/// the horizontal reader only.
const double readerPagedGap = AppSpacing.xs;

/// How far past the top of the viewport a page has to start before it counts as
/// the page being read. Without this lead a page is "current" only once its top
/// edge is exactly at the viewport edge, and the counter flickers between two
/// pages while the join crosses the top of the screen.
const double readerVisiblePageLead = 80;

/// The width/height ratio each page of a chapter is laid out with, for the life
/// of one reading session.
///
/// The backend has historically not stored page dimensions, and several sources
/// never report them, so most pages open on [defaultAspectRatio] and are
/// upgraded once the decoder tells us how tall the page really is.
///
/// A ratio is written **at most once**. Every change to a page's extent moves
/// every page after it along the scroll axis, so a page allowed to change height
/// twice would jerk the reader twice. First write wins.
///
/// Measurements are staged in [pendingRatios] rather than applied on the spot:
/// whoever owns the scroll position has to read the *old* geometry to work out
/// how far the pages below just moved, and it can only do that before the new
/// sizes land. Listeners are notified on submit and are expected to call
/// [commitPending].
class ReaderPageExtents extends ChangeNotifier {
  ReaderPageExtents(List<ReaderPage> pages)
      : _ratios = _ratiosFor(pages);

  /// Seed directly from ratios. ``null`` marks a page whose size is unknown.
  @visibleForTesting
  ReaderPageExtents.fromRatios(List<double?> ratios)
      : _ratios = List<double?>.of(ratios);

  /// Growable on purpose (spec R1/R2): a continuous feed gains a chapter's
  /// pages at either end as the reader approaches a seam, and every ratio
  /// already resolved has to survive that. Rebuilding this object instead
  /// would re-measure every page on screen and jerk the reader.
  final List<double?> _ratios;
  final Map<int, double> _pending = <int, double>{};

  static List<double?> _ratiosFor(List<ReaderPage> pages) => [
        for (final page in pages)
          _usableRatio(page.width?.toDouble(), page.height?.toDouble()),
      ];

  /// Adds [pages] after the last one. Indices already in use are untouched, so
  /// nothing above the viewport moves and no correction is needed.
  void appendPages(List<ReaderPage> pages) {
    if (pages.isEmpty) return;
    _ratios.addAll(_ratiosFor(pages));
  }

  /// Adds [pages] before the first one.
  ///
  /// **Every index shifts** by `pages.length`, including the keys of anything
  /// staged and not yet committed — remapped here rather than dropped, because
  /// a dropped measurement is a page that silently keeps a wrong height for
  /// the rest of the session. The caller still owes the scroll position a
  /// correction for the extent that just appeared above it.
  void prependPages(List<ReaderPage> pages) {
    if (pages.isEmpty) return;
    _ratios.insertAll(0, _ratiosFor(pages));
    _shiftPending(pages.length);
  }

  /// Drops the first [count] pages — the far-behind end of a Read-all window.
  void removeLeadingPages(int count) {
    final drop = count.clamp(0, _ratios.length);
    if (drop <= 0) return;
    _ratios.removeRange(0, drop);
    _shiftPending(-drop);
  }

  /// Drops the last [count] pages.
  void removeTrailingPages(int count) {
    final drop = count.clamp(0, _ratios.length);
    if (drop <= 0) return;
    _ratios.removeRange(_ratios.length - drop, _ratios.length);
    _pending.removeWhere((index, _) => index >= _ratios.length);
  }

  void _shiftPending(int delta) {
    if (_pending.isEmpty || delta == 0) return;
    final shifted = <int, double>{};
    for (final entry in _pending.entries) {
      final index = entry.key + delta;
      if (index >= 0 && index < _ratios.length) shifted[index] = entry.value;
    }
    _pending
      ..clear()
      ..addAll(shifted);
  }

  int get length => _ratios.length;

  /// ``true`` once this page's real size is known — from the payload or from a
  /// decode. A resolved page never changes extent again.
  bool isResolved(int index) =>
      index >= 0 && index < _ratios.length && _ratios[index] != null;

  /// Ratio to lay page [index] out with, falling back to [defaultAspectRatio]
  /// while the real size is still unknown.
  double ratioAt(int index) {
    if (index < 0 || index >= _ratios.length) return defaultAspectRatio;
    return _ratios[index] ?? defaultAspectRatio;
  }

  /// Every page's layout ratio, fallbacks included — the input to
  /// [ReaderPageMetrics]. A snapshot: metrics are immutable and must not see
  /// the list grow under them.
  List<double> get layoutRatios =>
      List<double>.generate(_ratios.length, ratioAt, growable: false);

  /// Sizes submitted but not yet folded into the layout.
  UnmodifiableMapView<int, double> get pendingRatios =>
      UnmodifiableMapView<int, double>(_pending);

  /// Stage a page's real decoded size. Ignored for an already-resolved page or
  /// an unusable size. Returns ``true`` when something was staged.
  bool submitMeasuredSize(
    int index, {
    required int pixelWidth,
    required int pixelHeight,
  }) {
    if (index < 0 || index >= _ratios.length) return false;
    if (_ratios[index] != null) return false;
    final ratio = _usableRatio(pixelWidth.toDouble(), pixelHeight.toDouble());
    if (ratio == null) return false;
    if (_pending[index] == ratio) return false;
    _pending[index] = ratio;
    notifyListeners();
    return true;
  }

  /// Fold every staged size into the layout.
  void commitPending() {
    if (_pending.isEmpty) return;
    for (final entry in _pending.entries) {
      _ratios[entry.key] ??= entry.value;
    }
    _pending.clear();
  }

  static double? _usableRatio(double? width, double? height) {
    if (width == null || height == null) return null;
    if (!width.isFinite || !height.isFinite) return null;
    if (width <= 0 || height <= 0) return null;
    return width / height;
  }
}

/// Where every page of a chapter sits along the scroll axis.
///
/// This is the reader's single source of geometry: the list is *forced* to
/// these extents (`itemExtentBuilder`), the page counter is derived from them,
/// and a page jump — the scrubber, a restore, a bookmark — resolves through
/// [offsetToPage]. Nothing gets to estimate independently, so nothing can
/// disagree.
@immutable
class ReaderPageMetrics {
  const ReaderPageMetrics({
    required this.ratios,
    required this.direction,
    required this.fitMode,
    required this.viewportWidth,
    required this.viewportHeight,
    this.zoom = 1,
    this.leadingInsets = const {},
  });

  factory ReaderPageMetrics.of(
    ReaderPageExtents extents, {
    required ReadingDirection direction,
    required ReaderFitMode fitMode,
    required double viewportWidth,
    required double viewportHeight,
    double zoom = 1,
    Map<int, double> leadingInsets = const {},
  }) =>
      ReaderPageMetrics(
        ratios: extents.layoutRatios,
        direction: direction,
        fitMode: fitMode,
        viewportWidth: viewportWidth,
        viewportHeight: viewportHeight,
        zoom: zoom,
        leadingInsets: leadingInsets,
      );

  final List<double> ratios;
  final ReadingDirection direction;
  final ReaderFitMode fitMode;
  final double viewportWidth;
  final double viewportHeight;
  final double zoom;

  /// Extra space reserved **above** particular pages, by index — the chapter
  /// seam divider (spec R1) and nothing else so far.
  ///
  /// Part of the geometry rather than a widget the list happens to contain,
  /// because everything here has to agree: a divider the list drew but the
  /// metrics did not know about would push every page after it out of the
  /// offsets the page counter, the scrub rail and every jump resolve to.
  final Map<int, double> leadingInsets;

  int get pageCount => ratios.length;

  double leadingInsetAt(int index) => leadingInsets[index] ?? 0;

  /// Width a page image is actually painted at.
  ///
  /// Mirrors the item tree exactly: up to 1x zoom the page is capped at
  /// [maxContentWidth] so a tablet does not stretch a phone-sized strip across
  /// the screen; past 1x the cap is lifted and the page deliberately overflows
  /// the viewport, which is what zooming in means here.
  double get contentWidth =>
      (zoom > 1 ? viewportWidth : math.min(viewportWidth, maxContentWidth)) *
      zoom;

  double ratioAt(int index) =>
      (index >= 0 && index < ratios.length) ? ratios[index] : defaultAspectRatio;

  /// Extent page [index] occupies along the scroll axis, its seam divider
  /// included — the number the list is forced to and every offset is summed
  /// from.
  double extentAt(int index) =>
      extentForRatio(ratioAt(index)) + leadingInsetAt(index);

  /// Extent a page of [ratio] would occupy along the scroll axis.
  double extentForRatio(double ratio) {
    final safe =
        (ratio.isFinite && ratio > 0) ? ratio : defaultAspectRatio;
    if (direction.isVertical) {
      return switch (fitMode) {
        // Webtoon case: the page spans the content width and its height falls
        // straight out of the ratio.
        ReaderFitMode.width => contentWidth / safe,
        // Fit height and fit screen letterbox every page into exactly one
        // screenful, so the ratio does not enter into it.
        ReaderFitMode.height || ReaderFitMode.screen => viewportHeight,
      };
    }
    // Paged reading: each page is one viewport tall, as wide as its ratio
    // makes it, plus the gap the list leaves after it.
    return viewportHeight * zoom * safe + readerPagedGap;
  }

  /// Scroll offset at which page [pageNumber] (1-based) starts.
  double offsetToPage(int pageNumber) {
    if (pageCount == 0) return 0;
    final target = (pageNumber - 1).clamp(0, pageCount - 1);
    var offset = readerListLeadingPadding;
    for (var index = 0; index < target; index++) {
      offset += extentAt(index);
    }
    return offset;
  }

  /// The 1-based page being read when the top of the viewport is at
  /// [scrollOffset].
  int pageAtOffset(double scrollOffset) {
    if (pageCount == 0) return 1;
    final probe = scrollOffset + readerVisiblePageLead;
    var cumulative = readerListLeadingPadding;
    var active = 1;
    for (var index = 0; index < pageCount; index++) {
      if (cumulative <= probe) active = index + 1;
      cumulative += extentAt(index);
    }
    return active;
  }

  /// Total extent of every page, excluding the list's own padding.
  ///
  /// Handed to the list so it reports the chapter's real scrollable range
  /// instead of extrapolating it from the average height of the few pages it
  /// happens to have laid out.
  double get totalPagesExtent {
    var total = 0.0;
    for (var index = 0; index < pageCount; index++) {
      total += extentAt(index);
    }
    return total;
  }
}

/// How far the scroll offset has to move when the extent reserved for one page
/// changes, so that what the reader is looking at stays where it was.
///
/// A list anchors its layout on the first child it has laid out, so growing a
/// page shoves everything after it further along the scroll axis by exactly the
/// growth. When that page is above the viewport the reader never sees it change
/// — all they see is the page they were reading slide away, which is the
/// reported "it randomly sent me to the pages above". Moving the offset by the
/// same amount cancels the shove out.
///
/// [pageStart] and [oldExtent] describe the page *before* the change;
/// [scrollOffset] is the top of the viewport in the same, pre-change geometry.
double scrollCorrectionForExtentChange({
  required double pageStart,
  required double oldExtent,
  required double newExtent,
  required double scrollOffset,
}) {
  final delta = newExtent - oldExtent;
  if (delta == 0 || !delta.isFinite) return 0;
  // The change begins at or below the top of the viewport: nothing the reader
  // can see has moved, and correcting would itself be the jump.
  if (pageStart >= scrollOffset) return 0;
  // Entirely above: everything below it — the whole visible screen — shifted by
  // the full delta.
  if (pageStart + oldExtent <= scrollOffset) return delta;
  // The page straddles the top of the viewport. Only the part above the edge
  // pushed, so compensate in proportion; that keeps the same point of this page
  // pinned to the top edge instead of rescaling the reader's position.
  if (oldExtent <= 0) return 0;
  final consumed = (scrollOffset - pageStart) / oldExtent;
  return delta * consumed;
}
