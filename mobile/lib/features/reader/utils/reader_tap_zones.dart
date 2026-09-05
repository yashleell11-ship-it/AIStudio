import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Fraction of the page width each outer band occupies. Thirds is what the
/// reader has always used, and it is the widest edge that still leaves a centre
/// a thumb can hit without turning a page.
const double readerTapEdgeRatio = 1 / 3;

/// The three bands a tap can land in, before any action is applied. Purely
/// geometric: only the ACTION a band performs is direction-aware, never the
/// band itself.
enum TapZonePosition { left, center, right }

/// Which band [dx] falls in on a page [width] wide.
///
/// Anything unmeasurable resolves to [TapZonePosition.center]: the centre is
/// the only band whose default action is reversible, so a tap the geometry
/// cannot place reveals the controls instead of silently moving the reader.
TapZonePosition tapZonePositionAt(
  double dx,
  double width, {
  double edgeRatio = readerTapEdgeRatio,
}) {
  if (!(width > 0)) return TapZonePosition.center;

  final ratio = dx / width;
  if (!ratio.isFinite || ratio < 0 || ratio > 1) return TapZonePosition.center;

  final edge = edgeRatio.clamp(0.0, 0.5);
  if (ratio < edge) return TapZonePosition.left;
  if (ratio > 1 - edge) return TapZonePosition.right;
  return TapZonePosition.center;
}

/// Resolve a tap at [dx] against an explicit [config].
///
/// [config] is required, not nullable: turning "never customised" into a
/// concrete default is the caller's job, because only the caller knows the
/// reading direction that default mirrors itself against
/// (see [TapZoneConfig.defaultFor]).
TapZoneAction resolveTapZone(
  double dx,
  double width,
  TapZoneConfig config, {
  double edgeRatio = readerTapEdgeRatio,
}) =>
    switch (tapZonePositionAt(dx, width, edgeRatio: edgeRatio)) {
      TapZonePosition.left => config.left,
      TapZonePosition.center => config.center,
      TapZonePosition.right => config.right,
    };
