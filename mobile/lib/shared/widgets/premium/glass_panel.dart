import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Raised panel, built the way the active design preset says to build one.
///
/// Under a glass preset this is what it always was — a backdrop blur behind a
/// translucent surface with a subtle border, mirroring the web `.glass-panel`.
/// Under a solid preset the blur is not merely set to zero: the
/// [BackdropFilter] is left out of the tree entirely, because a blur of 0 still
/// costs a saveLayer over everything behind the panel, and "faster to paint" is
/// half of what the solid presets are for.
///
/// The class name is unchanged so the ~30 call sites keep reading as one
/// idiom; what "glass" means is now the preset's answer, not a constant.
class GlassPanel extends StatelessWidget {
  const GlassPanel({
    super.key,
    required this.child,
    this.padding,
    this.borderRadius,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;

  /// Overrides the preset's default panel corner radius.
  final double? borderRadius;

  @override
  Widget build(BuildContext context) {
    final surfaces = context.surfaces;
    final br = BorderRadius.circular(borderRadius ?? context.radii.xl2);

    final panel = Container(
      padding: padding,
      decoration: BoxDecoration(
        color: context.colors.surface.withValues(alpha: surfaces.panelOpacity),
        borderRadius: br,
        border: Border.all(
          color: context.colors.border,
          width: context.strokes.border,
        ),
      ),
      // A transparent Material sits in front of the panel's background so
      // ListTile/SwitchListTile descendants paint their tint and ink on a
      // Material that isn't hidden by the panel's DecoratedBox color.
      child: Material(
        type: MaterialType.transparency,
        child: child,
      ),
    );

    return ClipRRect(
      borderRadius: br,
      child: surfaces.isGlass
          ? BackdropFilter(
              filter: ImageFilter.blur(
                sigmaX: surfaces.blurSigma,
                sigmaY: surfaces.blurSigma,
              ),
              child: panel,
            )
          : panel,
    );
  }
}

/// Applies the preset's *chrome* blur to [child], or nothing at all.
///
/// The floating bars — the bottom nav, the reader's controls — are their own
/// kind of surface: they hover over arbitrary artwork rather than resting on
/// the page, so they carry their own blur and alpha
/// ([AppSurfaceStyle.chromeBlurSigma] / [AppSurfaceStyle.chromeOpacity]).
/// Under a solid preset this returns [child] untouched, keeping the
/// [BackdropFilter] and its full-screen saveLayer out of the tree entirely
/// rather than running it with a zero sigma.
class ChromeBlur extends StatelessWidget {
  const ChromeBlur({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final surfaces = context.surfaces;
    if (!surfaces.isChromeGlass) return child;
    return BackdropFilter(
      filter: ImageFilter.blur(
        sigmaX: surfaces.chromeBlurSigma,
        sigmaY: surfaces.chromeBlurSigma,
      ),
      child: child,
    );
  }
}
