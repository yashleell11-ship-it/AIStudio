import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

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
    final radius = BorderRadius.circular(context.radii.pill);

    final content = Row(
      mainAxisSize: expanded ? MainAxisSize.max : MainAxisSize.min,
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (icon != null) ...[
          Icon(icon, size: 18, color: context.colors.fg),
          SizedBox(width: context.space.sm),
        ],
        Text(
          label.toUpperCase(),
          style: context.text.labelLg.copyWith(
            color: context.colors.fg,
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
        splashColor: context.colors.fg.withValues(alpha: 0.10),
        highlightColor: context.colors.fg.withValues(alpha: 0.06),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: radius,
            border: Border.all(color: context.colors.fg, width: 2),
          ),
          padding: EdgeInsets.symmetric(
            horizontal: context.space.xl2,
            vertical: context.space.md + 2,
          ),
          child: content,
        ),
      ),
    );
  }
}
