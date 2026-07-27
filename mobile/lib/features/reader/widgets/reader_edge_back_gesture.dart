import 'package:flutter/material.dart';

/// Left-edge swipe-to-leave for the reader, for the platforms and reading
/// modes where it is safe.
///
/// The reader is pushed as a `CustomTransitionPage` (a fade), which supplies
/// its own `transitionsBuilder` and therefore bypasses `PageTransitionsTheme`
/// entirely — `CupertinoPageTransitionsBuilder`, and with it the system
/// back-swipe, never runs inside a chapter. That is deliberate: in
/// left-to-right / right-to-left mode the page list is a horizontal
/// `ListView`, so a system edge gesture would compete for exactly the drags
/// that turn pages. It leaves an iPhone with no hardware back button and a
/// 3-second control auto-hide with no gestural way out.
///
/// Vertical (webtoon) mode — the default — scrolls on the other axis and has
/// no horizontal drag to conflict with, so the platform gesture can be handed
/// back there. [enabled] is what the caller uses to express that; see
/// `ReaderContent.build`.
///
/// Must be a direct child of a [Stack]: it positions itself along the leading
/// edge.
class ReaderEdgeBackGesture extends StatefulWidget {
  const ReaderEdgeBackGesture({
    super.key,
    required this.enabled,
    required this.onBack,
  });

  /// Width of the drag-sensitive strip, matching Cupertino's own
  /// `_kBackGestureWidth`.
  static const double edgeWidth = 20;

  /// Fraction of the screen width a *slow* drag must cover to count as "back" —
  /// Cupertino's halfway-point rule (`controller.value > 0.5`). Kept strict
  /// deliberately: this gesture has no visual tracking to warn you it is about
  /// to fire, so a fling is the intended trigger and the distance rule is only
  /// the fallback.
  static const double dragDistanceFraction = 0.5;

  /// Fling speed that dismisses regardless of distance, in *screen widths per
  /// second* — the same unit and the same 1.0 threshold as Cupertino's
  /// `_kMinFlingVelocity`, so a real iOS back-flick feels identical here.
  static const double minFlingVelocity = 1.0;

  /// When false this renders nothing at all, so the strip cannot sit in the
  /// hit-test path of a horizontally paged reader.
  final bool enabled;

  final VoidCallback onBack;

  @override
  State<ReaderEdgeBackGesture> createState() => _ReaderEdgeBackGestureState();
}

class _ReaderEdgeBackGestureState extends State<ReaderEdgeBackGesture> {
  /// Distance dragged towards the trailing edge since the gesture started, in
  /// logical pixels. Deliberately not in `setState` — nothing about this widget
  /// is painted, so tracking it must not schedule a frame while the reader is
  /// mid-scroll.
  double _dragged = 0;

  @override
  Widget build(BuildContext context) {
    if (!widget.enabled) return const SizedBox.shrink();

    final isRtl = Directionality.of(context) == TextDirection.rtl;

    return Positioned(
      top: 0,
      bottom: 0,
      left: isRtl ? null : 0,
      right: isRtl ? 0 : null,
      width: ReaderEdgeBackGesture.edgeWidth,
      child: GestureDetector(
        // Translucent, not opaque: taps and vertical scrolls in this strip must
        // still reach the page list and the reader's tap-zone detector beneath.
        // A horizontal drag recogniser loses the arena to both of those.
        behavior: HitTestBehavior.translucent,
        onHorizontalDragStart: (_) => _dragged = 0,
        onHorizontalDragUpdate: (details) =>
            _dragged += isRtl ? -details.delta.dx : details.delta.dx,
        onHorizontalDragCancel: () => _dragged = 0,
        onHorizontalDragEnd: (details) {
          final travelled = _dragged;
          _dragged = 0;
          final width = MediaQuery.sizeOf(context).width;
          if (width <= 0) return;
          final pxPerSecond = isRtl
              ? -details.velocity.pixelsPerSecond.dx
              : details.velocity.pixelsPerSecond.dx;
          final flung = pxPerSecond / width >=
              ReaderEdgeBackGesture.minFlingVelocity;
          final dragged =
              travelled >= width * ReaderEdgeBackGesture.dragDistanceFraction;
          if (flung || dragged) widget.onBack();
        },
      ),
    );
  }
}
