import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

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
      padding: const EdgeInsets.only(bottom: AppSpacing.xl),
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
              borderRadius: BorderRadius.circular(AppRadius.full),
            ),
          ),
          const SizedBox(width: AppSpacing.md),
          Icon(icon, size: 15, color: context.colors.cyan400),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Text(
              title.toUpperCase(),
              style: AppTypography.label.copyWith(
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
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.xs,
                ),
                decoration: BoxDecoration(
                  color: context.colors.fg.withAlpha(10),
                  borderRadius: BorderRadius.circular(AppRadius.full),
                  border: Border.all(color: context.colors.border.withAlpha(100)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      viewAllLabel,
                      style: AppTypography.caption.copyWith(
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
