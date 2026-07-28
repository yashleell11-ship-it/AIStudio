import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// One labelled pill in a [SeriesDetailChipRow].
class SeriesDetailChip {
  const SeriesDetailChip({required this.label, this.color});

  final String label;

  /// Accent for chips that carry meaning (reading status, a coloured tag).
  /// Null renders the neutral treatment.
  final Color? color;
}

/// Wrapping row of metadata pills — reading status, language, year, tags,
/// genres.
///
/// One widget for every chip either series page shows, so a library tag and a
/// source genre cannot end up as two different-looking things that mean the
/// same thing to the reader.
class SeriesDetailChipRow extends StatelessWidget {
  const SeriesDetailChipRow({super.key, required this.chips});

  final List<SeriesDetailChip> chips;

  @override
  Widget build(BuildContext context) {
    if (chips.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: AppSpacing.sm,
      runSpacing: AppSpacing.sm,
      children: [
        for (final chip in chips)
          Container(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.xs,
            ),
            decoration: BoxDecoration(
              color: (chip.color ?? AppColors.fg).withAlpha(13),
              borderRadius: BorderRadius.circular(AppRadius.full),
              border: Border.all(color: AppColors.border.withAlpha(128)),
            ),
            child: Text(
              chip.label,
              style: AppTypography.caption.copyWith(
                color: chip.color ?? AppColors.muted,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
      ],
    );
  }
}
