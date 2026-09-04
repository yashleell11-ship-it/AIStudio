import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Premium glass card with subtle gradient highlight and optional accent glow.
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
    final radius = borderRadius ?? context.radii.xl;
    final br = BorderRadius.circular(radius);

    final card = Container(
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: br,
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            context.colors.surface2.withAlpha(180),
            context.colors.panel,
          ],
          stops: const [0.0, 1.0],
        ),
        border: Border.all(color: context.colors.glassEdge),
        boxShadow: glowColor != null
            ? [
                BoxShadow(
                  color: glowColor!.withAlpha(28),
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
