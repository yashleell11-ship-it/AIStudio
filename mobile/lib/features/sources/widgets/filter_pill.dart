import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Selectable pill for the Sources and Search filter rows.
///
/// A fixed-height pill rather than a Material [FilterChip] because both filter
/// rows sit inside sliver headers with a declared extent — chip theming can
/// change their intrinsic height, this cannot.
class FilterPill extends StatelessWidget {
  const FilterPill({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.count,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  /// Optional trailing count, e.g. how many sources match the filter.
  final int? count;

  static const double height = 34;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? AppColors.primaryFg : AppColors.muted;

    return Material(
      color: selected ? AppColors.primary : AppColors.fg.withAlpha(13),
      borderRadius: BorderRadius.circular(AppRadius.full),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.full),
        child: Container(
          height: height,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.full),
            border: Border.all(
              color: selected
                  ? Colors.transparent
                  : AppColors.border.withAlpha(128),
            ),
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: AppTypography.label.copyWith(
                  color: foreground,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                ),
              ),
              if (count != null) ...[
                const SizedBox(width: AppSpacing.xs),
                Text(
                  '$count',
                  style: AppTypography.labelSm.copyWith(
                    color: foreground.withAlpha(selected ? 200 : 150),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
