import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

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
    final foreground = selected ? context.colors.primaryFg : context.colors.muted;

    return Material(
      color: selected ? context.colors.primary : context.colors.fg.withAlpha(13),
      borderRadius: BorderRadius.circular(context.radii.full),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(context.radii.full),
        child: Container(
          height: height,
          padding: EdgeInsets.symmetric(horizontal: context.space.lg),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(context.radii.full),
            border: Border.all(
              color: selected
                  ? Colors.transparent
                  : context.colors.border.withAlpha(128),
            ),
          ),
          alignment: Alignment.center,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                label,
                style: context.text.label.copyWith(
                  color: foreground,
                  fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                ),
              ),
              if (count != null) ...[
                SizedBox(width: context.space.xs),
                Text(
                  '$count',
                  style: context.text.labelSm.copyWith(
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
