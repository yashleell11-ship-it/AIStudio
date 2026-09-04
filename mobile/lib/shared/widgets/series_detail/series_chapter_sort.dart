import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Chapter list ordering. Defaults to newest-first (highest chapter number).
///
/// Shared by the library (downloaded) and source (catalog) series pages: the
/// same control has to mean the same thing on both, otherwise the two pages
/// order "the same" list differently and only one of them can be right.
enum SeriesChapterSortOrder { newest, oldest }

/// Returns a copy of [chapters] ordered by chapter number.
///
/// Newest = descending, oldest = ascending, and chapters with no number are
/// always last in both directions — an unnumbered extra sorts to the end rather
/// than jumping to the top when the toggle flips.
///
/// The sort is made stable by tie-breaking on the original index: `List.sort`
/// is not stable in Dart, so a hand-imported series whose chapters all have a
/// null number (every comparison equal) would otherwise come back scrambled,
/// and differently scrambled on each rebuild.
List<T> sortSeriesChapters<T>(
  List<T> chapters, {
  required double? Function(T chapter) numberOf,
  required SeriesChapterSortOrder order,
}) {
  final indexed = <({int index, T value})>[
    for (var i = 0; i < chapters.length; i++) (index: i, value: chapters[i]),
  ];
  indexed.sort((a, b) {
    final an = numberOf(a.value);
    final bn = numberOf(b.value);
    if (an == null && bn == null) return a.index.compareTo(b.index);
    if (an == null) return 1;
    if (bn == null) return -1;
    final comparison = order == SeriesChapterSortOrder.newest
        ? bn.compareTo(an)
        : an.compareTo(bn);
    return comparison != 0 ? comparison : a.index.compareTo(b.index);
  });
  return [for (final entry in indexed) entry.value];
}

/// Compact Newest/Oldest segmented toggle for the chapter list header.
class SeriesChapterSortToggle extends StatelessWidget {
  const SeriesChapterSortToggle({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final SeriesChapterSortOrder value;
  final ValueChanged<SeriesChapterSortOrder> onChanged;

  @override
  Widget build(BuildContext context) {
    final motion = MediaQuery.disableAnimationsOf(context)
        ? Duration.zero
        : const Duration(milliseconds: 150);
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: context.colors.surface2,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: context.colors.glassEdge),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _segment(context, 'Newest', SeriesChapterSortOrder.newest, motion),
          _segment(context, 'Oldest', SeriesChapterSortOrder.oldest, motion),
        ],
      ),
    );
  }

  Widget _segment(
    BuildContext context,
    String label,
    SeriesChapterSortOrder order,
    Duration motion,
  ) {
    final selected = value == order;
    return GestureDetector(
      onTap: selected ? null : () => onChanged(order),
      child: AnimatedContainer(
        duration: motion,
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: selected ? context.colors.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Text(
          label,
          style: AppTypography.caption.copyWith(
            color: selected ? context.colors.primaryFg : context.colors.muted,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
      ),
    );
  }
}
