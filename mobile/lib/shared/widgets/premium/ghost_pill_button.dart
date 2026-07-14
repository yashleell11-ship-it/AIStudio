import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Secondary "ghost" pill — transparent with a 2px foreground border.
///
/// Mirrors the web `GhostPillButton`: `border-2 border-fg`, uppercase label,
/// foreground text, and a subtle fill on press (web hover `bg-fg/10`).
class GhostPillButton extends StatelessWidget {
  const GhostPillButton({
    super.key,
    this.label = 'Browse Sources',
    this.onPressed,
    this.icon,
    this.expanded = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  /// When true the pill stretches to fill its parent's width.
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    final radius = BorderRadius.circular(AppRadius.pill);

    final content = Row(
      mainAxisSize: expanded ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: AppColors.fg),
          const SizedBox(width: AppSpacing.sm),
        ],
        Text(
          label.toUpperCase(),
          style: AppTypography.labelLg.copyWith(
            color: AppColors.fg,
            fontWeight: FontWeight.w500,
            letterSpacing: 1.2,
          ),
        ),
      ],
    );

    return Material(
      type: MaterialType.transparency,
      child: InkWell(
        onTap: onPressed,
        borderRadius: radius,
        splashColor: AppColors.fg.withValues(alpha: 0.10),
        highlightColor: AppColors.fg.withValues(alpha: 0.06),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: AppColors.fg, width: 2),
          ),
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl2,
            vertical: AppSpacing.md + 2,
          ),
          child: content,
        ),
      ),
    );
  }
}
