import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';

/// Cover + identity block at the top of both series pages.
///
/// Owns the whole treatment — the 2:3 cover, the title scale, the credit lines,
/// the summary line and the description — so the library and source pages can
/// only ever render it the same way. They differ in where the facts come from,
/// never in how they look.
class SeriesDetailHeader extends StatelessWidget {
  const SeriesDetailHeader({
    super.key,
    this.cover,
    required this.title,
    this.originalTitle,
    this.author,
    this.artist,
    this.metaLine,
    this.description,
  });

  /// The cover image. Null renders the empty-cover placeholder — used for a
  /// source that returned no cover URL, and for a library series with no
  /// extracted cover.
  final Widget? cover;

  final String title;

  /// Romanised/native title, when the series has one worth showing.
  final String? originalTitle;

  final String? author;
  final String? artist;

  /// Pre-built summary line — see `seriesDetailMetaLine`.
  final String? metaLine;

  final String? description;

  @override
  Widget build(BuildContext context) {
    final trimmedDescription = description?.trim();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: AspectRatio(
            aspectRatio: 2 / 3,
            child: cover ?? const ColoredBox(color: AppColors.panel),
          ),
        ),
        const SizedBox(height: AppSpacing.xl2),
        Text(title, style: AppTypography.displayMd),
        if (originalTitle != null && originalTitle!.trim().isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            originalTitle!,
            style: AppTypography.body.copyWith(
              color: AppColors.muted,
              fontStyle: FontStyle.italic,
            ),
          ),
        ],
        if (author != null && author!.trim().isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            author!,
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
        ],
        if (artist != null && artist!.trim().isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xxs),
          Text('Art by ${artist!}', style: AppTypography.caption),
        ],
        if (metaLine != null && metaLine!.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            metaLine!,
            style: AppTypography.label.copyWith(color: AppColors.primary),
          ),
        ],
        if (trimmedDescription != null && trimmedDescription.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          Text(trimmedDescription, style: AppTypography.body),
        ],
      ],
    );
  }
}
