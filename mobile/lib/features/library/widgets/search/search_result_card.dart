import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/features/library/widgets/library/library_skeleton.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class SearchResultCard extends ConsumerWidget {
  const SearchResultCard({
    super.key,
    required this.series,
    required this.onTap,
    required this.onToggleFavorite,
  });

  final FollowedSeries series;
  final VoidCallback onTap;
  final VoidCallback onToggleFavorite;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final tappable = series.chapterCount > 0;

    return GlassCard(
      onTap: tappable ? onTap : null,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SeriesCoverImage(
            url: followedSeriesCoverUrl(baseUrl, series) ?? '',
            width: 80,
            height: 120,
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        series.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.labelLg.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    _Badge(isFavorite: series.isFavorite),
                    IconButton(
                      onPressed: onToggleFavorite,
                      icon: Icon(
                        series.isFavorite ? Icons.star : Icons.star_border,
                        color: series.isFavorite
                            ? context.colors.warning
                            : context.colors.muted,
                      ),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(
                        minWidth: 32,
                        minHeight: 32,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  '${series.chapterCount} chapters',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.bodySm.copyWith(
                    color: context.colors.muted.withAlpha(204),
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                if (series.readingStatus.isNotEmpty)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: context.colors.fg.withAlpha(13),
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                    ),
                    child: Text(
                      readingStatusLabel(series.readingStatus).toUpperCase(),
                      style: AppTypography.caption.copyWith(
                        color: context.colors.muted,
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.isFavorite});

  final bool isFavorite;

  @override
  Widget build(BuildContext context) {
    if (isFavorite) {
      return Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.star, size: 14, color: context.colors.warning),
          const SizedBox(width: 4),
          Text(
            'Fav',
            style: AppTypography.caption.copyWith(color: context.colors.warning),
          ),
        ],
      );
    }

    return const SizedBox.shrink();
  }
}

class SearchResultCardSkeleton extends StatelessWidget {
  const SearchResultCardSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return const GlassCard(
      padding: EdgeInsets.all(AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBox(width: 80, height: 120, borderRadius: AppRadius.lg),
          SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SkeletonBox(width: double.infinity, height: 18),
                SizedBox(height: AppSpacing.sm),
                SkeletonBox(width: 120, height: 14),
                SizedBox(height: AppSpacing.md),
                SkeletonBox(width: double.infinity, height: 40),
                SizedBox(height: AppSpacing.md),
                SkeletonBox(width: 80, height: 12),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class SearchResultsSkeleton extends StatelessWidget {
  const SearchResultsSkeleton({super.key, this.viewMode = LibraryViewMode.list});

  final LibraryViewMode viewMode;

  @override
  Widget build(BuildContext context) {
    if (viewMode == LibraryViewMode.grid) {
      return LibrarySkeleton(viewMode: viewMode);
    }

    return Column(
      children: List.generate(
        4,
        (_) => const Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.md),
          child: SearchResultCardSkeleton(),
        ),
      ),
    );
  }
}