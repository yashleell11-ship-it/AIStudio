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
      : _ratios = List<double?>.generate(
          pages.length,
          (index) => _usableRatio(
            pages[index].width?.toDouble(),
            pages[index].height?.toDouble(),
          ),
          growable: false,
        );

  /// Seed directly from ratios. ``null`` marks a page whose size is unknown.
  @visibleForTesting
  ReaderPageExtents.fromRatios(List<double?> ratios)
      : _ratios = List<double?>.of(ratios, growable: false);

  final List<double?> _ratios;
  final Map<int, double> _pending = <int, double>{};

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
  /// [ReaderPageMetrics].
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
  });

  factory ReaderPageMetrics.of(
    ReaderPageExtents extents, {
    required ReadingDirection direction,
    required ReaderFitMode fitMode,
    required double viewportWidth,
    required double viewportHeight,
    double zoom = 1,
  }) =>
      ReaderPageMetrics(
        ratios: extents.layoutRatios,
        direction: direction,
        fitMode: fitMode,
        viewportWidth: viewportWidth,
        viewportHeight: viewportHeight,
        zoom: zoom,
      );

  final List<double> ratios;
  final ReadingDirection direction;
  final ReaderFitMode fitMode;
  final double viewportWidth;
  final double viewportHeight;
  final double zoom;

  int get pageCount => ratios.length;

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

  /// Extent page [index] occupies along the scroll axis.
  double extentAt(int index) => extentForRatio(ratioAt(index));

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
