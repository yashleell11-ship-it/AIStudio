import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// The app's card surface, dressed by the active design preset.
///
/// Signature and the other glass presets keep the shipped treatment — a
/// top-to-bottom highlight gradient, a soft glass edge, and an optional
/// ambient glow. Solid presets flatten all three: one opaque fill, a
/// full-strength hairline you are meant to see, and no shadow. The gradient
/// and the glow are dropped rather than faded to nothing, so a flat preset
/// really is cheaper to paint and not just quieter to look at.
///
/// Colours stay the palette's throughout — the preset only decides *how*
/// the surface is constructed, never what shade it is.
class GlassCard extends StatelessWidget {
  const GlassCard({
    super.key,
    required this.child,
    this.padding,
    this.onTap,
    this.glowColor,
    this.borderRadius,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final VoidCallback? onTap;

  /// Optional color for a subtle ambient glow behind the card.
  final Color? glowColor;

  /// Override border radius (defaults to context.radii.xl).
  final double? borderRadius;

  @override
  Widget build(BuildContext context) {
    final surfaces = context.surfaces;
    final radius = borderRadius ?? context.radii.xl;
    final br = BorderRadius.circular(radius);
    final glow = glowColor;

    final card = Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: br,
        color: surfaces.gradientCards
            ? null
            : context.colors.panel.withValues(alpha: surfaces.cardOpacity),
        gradient: surfaces.gradientCards
            ? LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  context.colors.surface2.withAlpha(180),
                  context.colors.panel,
                ],
                stops: const [0.0, 1.0],
              )
            : null,
        border: Border.all(
          color: surfaces.cardBorderIsStrong
              ? context.colors.border
              : context.colors.glassEdge,
          width: context.strokes.border,
        ),
        boxShadow: glow != null && surfaces.glowAlpha > 0
            ? [
                BoxShadow(
                  color: glow.withAlpha(surfaces.glowAlpha.round()),
                  blurRadius: 20,
                  spreadRadius: -4,
                ),
              ]
            : null,
      ),
      padding: padding,
      child: child,
    );

    return Material(
      color: Colors.transparent,
      child: onTap == null
          ? card
          : InkWell(
              onTap: onTap,
              borderRadius: br,
              splashColor: context.colors.fg.withAlpha(10),
              highlightColor: context.colors.fg.withAlpha(6),
              child: card,
            ),
    );
  }
}
