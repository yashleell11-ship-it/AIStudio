import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';
import 'package:manhwamaniacs/features/sources/utils/source_branding.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// List-style result row for a federated search hit. Renders the API-provided
/// (absolute) [GlobalSearchItem.coverUrl] via [SeriesCoverImage] and tags remote
/// hits with a source badge so the user can tell library results apart from
/// results pulled live from an external source.
class GlobalSearchResultCard extends StatelessWidget {
  const GlobalSearchResultCard({
    super.key,
    required this.item,
    required this.onTap,
  });

  final GlobalSearchItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SeriesCoverImage(
            url: item.coverUrl ?? '',
            width: 72,
            height: 108,
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.labelLg.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (item.author != null && item.author!.trim().isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(
                    item.author!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                  ),
                ],
                const SizedBox(height: AppSpacing.md),
                SourceBadge(item: item),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Compact cover-first card for the search results grid.
class GlobalSearchResultGridCard extends StatelessWidget {
  const GlobalSearchResultGridCard({
    super.key,
    required this.item,
    required this.onTap,
  });

  final GlobalSearchItem item;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.md),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(AppRadius.md),
            border: Border.all(color: AppColors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                flex: 6,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    SeriesCoverImage(url: item.coverUrl ?? '', borderRadius: 0),
                    Positioned(
                      left: AppSpacing.xxs,
                      top: AppSpacing.xxs,
                      child: SourceBadge(item: item, compact: true),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.xs,
                    vertical: AppSpacing.xxs,
                  ),
                  child: Text(
                    item.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption.copyWith(
                      color: AppColors.fg,
                      fontSize: 10,
                      height: 1.2,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Small pill identifying where a result came from: "Library" for local hits,
/// or the prettified source name (e.g. "MangaDex") for remote hits.
class SourceBadge extends StatelessWidget {
  const SourceBadge({super.key, required this.item, this.compact = false});

  final GlobalSearchItem item;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final isLocal = item.isLocal;
    final label = isLocal
        ? 'Library'
        : prettifySourceId(item.source ?? 'source');
    final color = isLocal ? AppColors.cyan400 : AppColors.violet400;

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? AppSpacing.xs : AppSpacing.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: compact
            ? AppColors.bg.withAlpha(204)
            : color.withAlpha(28),
        borderRadius: BorderRadius.circular(AppRadius.sm),
        border: Border.all(color: color.withAlpha(compact ? 120 : 77)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            isLocal ? Icons.bookmark_outline : Icons.public,
            size: 11,
            color: color,
          ),
          const SizedBox(width: 4),
          Text(
            label.toUpperCase(),
            style: AppTypography.caption.copyWith(
              color: color,
              fontSize: compact ? 8 : 10,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
            ),
          ),
        ],
      ),
    );
  }
}
