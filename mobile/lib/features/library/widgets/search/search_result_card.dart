import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
      padding: EdgeInsets.all(context.space.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SeriesCoverImage(
            url: followedSeriesCoverUrl(baseUrl, series) ?? '',
            width: 80,
            height: 120,
          ),
          SizedBox(width: context.space.lg),
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
                        style: context.text.labelLg.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                    SizedBox(width: context.space.sm),
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
                SizedBox(height: context.space.sm),
                Text(
                  '${series.chapterCount} chapters',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: context.text.bodySm.copyWith(
                    color: context.colors.muted.withAlpha(204),
                    height: 1.5,
                  ),
                ),
                SizedBox(height: context.space.md),
                if (series.readingStatus.isNotEmpty)
                  Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: context.space.sm,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: context.colors.fg.withAlpha(13),
                      borderRadius: BorderRadius.circular(context.radii.sm),
                    ),
                    child: Text(
                      readingStatusLabel(series.readingStatus).toUpperCase(),
                      style: context.text.caption.copyWith(
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
            style: context.text.caption.copyWith(color: context.colors.warning),
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
    return GlassCard(
      padding: EdgeInsets.all(context.space.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SkeletonBox(width: 80, height: 120, borderRadius: context.radii.lg),
          SizedBox(width: context.space.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SkeletonBox(width: double.infinity, height: 18),
                SizedBox(height: context.space.sm),
                const SkeletonBox(width: 120, height: 14),
                SizedBox(height: context.space.md),
                const SkeletonBox(width: double.infinity, height: 40),
                SizedBox(height: context.space.md),
                const SkeletonBox(width: 80, height: 12),
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
        (_) => Padding(
          padding: EdgeInsets.only(bottom: context.space.md),
          child: const SearchResultCardSkeleton(),
        ),
      ),
    );
  }
}