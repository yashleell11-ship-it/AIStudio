import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

class SectionHeader extends StatelessWidget {
  const SectionHeader({
    super.key,
    required this.icon,
    required this.title,
    this.onViewAll,
    this.viewAllLabel = 'View All',
  });

  final IconData icon;
  final String title;
  final VoidCallback? onViewAll;
  final String viewAllLabel;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.xl),
      child: Row(
        children: [
          // Left accent bar
          Container(
            width: 3,
            height: 18,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [context.colors.cyan400, context.colors.primary],
              ),
              borderRadius: BorderRadius.circular(context.radii.full),
            ),
          ),
          SizedBox(width: context.space.md),
          Icon(icon, size: 15, color: context.colors.cyan400),
          SizedBox(width: context.space.xs),
          Expanded(
            child: Text(
              title.toUpperCase(),
              style: context.text.label.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 1.4,
                color: context.colors.fg,
              ),
            ),
          ),
          if (onViewAll != null)
            GestureDetector(
              onTap: onViewAll,
              child: Container(
                constraints: const BoxConstraints(minHeight: 44),
                alignment: Alignment.center,
                padding: EdgeInsets.symmetric(
                  horizontal: context.space.md,
                  vertical: context.space.xs,
                ),
                decoration: BoxDecoration(
                  color: context.colors.fg.withAlpha(10),
                  borderRadius: BorderRadius.circular(context.radii.full),
                  border: Border.all(color: context.colors.border.withAlpha(100)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      viewAllLabel,
                      style: context.text.caption.copyWith(
                        color: context.colors.muted,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(width: 2),
                    Icon(Icons.chevron_right, size: 14, color: context.colors.muted),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
