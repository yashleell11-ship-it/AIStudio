import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Primary call-to-action pill using the warm "cta-gradient".
///
/// Mirrors the web `PrimaryPillButton`: a rounded-full pill filled with the
/// 123deg warm gradient, a white 2px inset outline, a warm glow shadow, and an
/// uppercase DM Sans label in white.
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

  /// The warm CTA gradient (matches web `.cta-gradient`, ~123deg).
  static const LinearGradient _ctaGradient = LinearGradient(
    // 123deg ≈ pointing toward lower-right; approximated with begin/end.
    begin: Alignment(-0.85, -1),
    end: Alignment(0.85, 1),
    colors: [
      Color(0xFF1A0A00),
      Color(0xFFBE4C00),
      Color(0xFFC2410C),
      Color(0xFFF59E0B),
    ],
    stops: [0.07, 0.37, 0.72, 1.0],
  );

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppRadius.pill);

    final content = Row(
      mainAxisSize: expanded ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: Colors.white),
          const SizedBox(width: AppSpacing.sm),
        ],
        Flexible(
          child: Text(
            label.toUpperCase(),
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: AppTypography.labelLg.copyWith(
              color: Colors.white,
              fontWeight: FontWeight.w500,
              letterSpacing: 1.2,
            ),
          ),
        ),
      ],
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: _ctaGradient,
        borderRadius: radius,
        boxShadow: [
          // Warm outer glow (--shadow-glow) + inset-like ambient depth.
          BoxShadow(
            color: context.colors.primary.withValues(alpha: 0.28),
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
          splashColor: Colors.white.withValues(alpha: 0.16),
          highlightColor: Colors.white.withValues(alpha: 0.08),
          child: Container(
            decoration: BoxDecoration(
              borderRadius: radius,
              // 2px white outline sitting inside the pill (outline-offset:-3).
              border: Border.all(color: Colors.white, width: 2),
            ),
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl2,
              vertical: AppSpacing.md + 2,
            ),
            child: content,
          ),
        ),
      ),
    );
  }
}
