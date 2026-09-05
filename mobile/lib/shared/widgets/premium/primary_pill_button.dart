import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Primary call-to-action pill — the app's most prominent control.
///
/// Mirrors the web `.cta-gradient`: a rounded-full pill filled with a ~123deg
/// ramp from the palette's primary-hover to its primary, a 2px inset outline,
/// a glow shadow, and an uppercase DM Sans label.
///
/// Every colour is a palette role. It used to hold four literal Eclipse hexes
/// (a near-black-to-amber ramp with a hard white outline), which meant the
/// button on the login, register and setup screens — the screens that can only
/// ever paint the default, because the theme key is per `(user, profile)` and
/// neither exists yet — stayed amber whatever the app's default was. The white
/// label was the same bet in miniature: legible over the dark end of that one
/// ramp and nowhere else.
class PrimaryPillButton extends StatelessWidget {
  const PrimaryPillButton({
    super.key,
    this.label = 'Continue Reading',
    this.onPressed,
    this.icon,
    this.expanded = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  /// When true the pill stretches to fill its parent's width.
  final bool expanded;

  /// The CTA ramp: deeper primary into brighter primary, which is the same
  /// direction in every palette. Stops match the web rule exactly
  /// (`primary-hover 0%, primary-hover 30%, primary 100%`).
  static LinearGradient _ctaGradient(AppPalette colors) => LinearGradient(
    // 123deg ≈ pointing toward lower-right; approximated with begin/end.
    begin: const Alignment(-0.85, -1),
    end: const Alignment(0.85, 1),
    colors: [colors.primaryHover, colors.primaryHover, colors.primary],
    stops: const [0.0, 0.3, 1.0],
  );

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(context.radii.pill);
    final colors = context.colors;
    // The label colour each palette nominates for a filled primary surface —
    // the one pairing the contrast suite holds to AA.
    final onPrimary = colors.primaryFg;

    final content = Row(
      mainAxisSize: expanded ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: onPrimary),
          SizedBox(width: context.space.sm),
        ],
        Flexible(
          child: Text(
            label.toUpperCase(),
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: context.text.labelLg.copyWith(
              color: onPrimary,
              fontWeight: FontWeight.w500,
              letterSpacing: 1.2,
            ),
          ),
        ),
      ],
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: _ctaGradient(colors),
        borderRadius: radius,
        boxShadow: [
          // Outer glow (--shadow-glow) + inset-like ambient depth.
          BoxShadow(
            color: colors.primary.withValues(alpha: 0.28),
            blurRadius: 24,
            spreadRadius: -2,
          ),
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.30),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Material(
        type: MaterialType.transparency,
        child: InkWell(
          onTap: onPressed,
          borderRadius: radius,
          splashColor: onPrimary.withValues(alpha: 0.16),
          highlightColor: onPrimary.withValues(alpha: 0.08),
          child: Container(
            decoration: BoxDecoration(
              borderRadius: radius,
              // 2px outline sitting inside the pill (outline-offset:-3), at
              // the same 35% of the label colour the web rule uses.
              border: Border.all(
                color: onPrimary.withValues(alpha: 0.35),
                width: 2,
              ),
            ),
            padding: EdgeInsets.symmetric(
              horizontal: context.space.xl2,
              vertical: context.space.md + 2,
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}
