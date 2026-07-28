import 'package:flutter/widgets.dart';

/// A [ScrollController] whose position can absorb a change in the size of the
/// content *above* the viewport.
///
/// When a page the reader has already scrolled past finally reports its real
/// height, every page after it moves along the scroll axis by the difference —
/// and the page they are actually looking at slides out from under their eyes.
/// That is the reported "when I scroll down it randomly sent me to the pages
/// above".
///
/// Compensating with [ScrollController.jumpTo] would also stop any fling dead
/// and dispatch scroll start/end notifications, which the reader reads as user
/// activity (tap cooldown, control auto-hide). [ScrollPosition.correctBy] is the
/// mechanism the framework itself uses for exactly this case — a sliver
/// returning `scrollOffsetCorrection` during layout: it shifts the offset,
/// tells nobody the user scrolled, and flags the position as corrected so an
/// in-flight ballistic simulation is re-derived from the new offset at the next
/// layout instead of snapping back. It is `@protected`, which is the only
/// reason this subclass exists.
class ReaderScrollController extends ScrollController {
  @override
  ReaderScrollPosition createScrollPosition(
    ScrollPhysics physics,
    ScrollContext context,
    ScrollPosition? oldPosition,
  ) {
    return ReaderScrollPosition(
      physics: physics,
      context: context,
      initialPixels: initialScrollOffset,
      keepScrollOffset: keepScrollOffset,
      oldPosition: oldPosition,
      debugLabel: debugLabel,
    );
  }

  /// Shift the offset by [delta] to cancel out content above the viewport
  /// changing size. Silently does nothing when there is no position yet.
  void applyExtentCorrection(double delta) {
    if (delta == 0 || !delta.isFinite || !hasClients) return;
    for (final position in positions) {
      if (position is ReaderScrollPosition) {
        position.applyExtentCorrection(delta);
      }
    }
  }
}

/// The position behind [ReaderScrollController]. See that class for why.
class ReaderScrollPosition extends ScrollPositionWithSingleContext {
  ReaderScrollPosition({
    required super.physics,
    required super.context,
    super.initialPixels,
    super.keepScrollOffset,
    super.oldPosition,
    super.debugLabel,
  });

  /// Move the offset by [delta] without it counting as a scroll.
  ///
  /// The caller is responsible for the layout that reads the corrected offset;
  /// [ScrollPosition.correctBy] deliberately notifies no one, exactly so a
  /// correction cannot be mistaken for the user moving.
  void applyExtentCorrection(double delta) {
    if (delta == 0 || !delta.isFinite || !hasPixels) return;
    correctBy(delta);
  }
}
