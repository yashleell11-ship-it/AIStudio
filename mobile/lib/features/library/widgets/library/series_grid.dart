import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/utils/responsive.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/utils/cover_url.dart';
import 'package:aistudio_mobile/features/library/utils/series_display.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/series_cover_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

class SeriesCard extends ConsumerWidget {
  const SeriesCard({
    super.key,
    required this.series,
    required this.onTap,
    required this.onToggleFavorite,
    this.onRemove,
  });

  final SeriesSummary series;
  final VoidCallback onTap;
  final VoidCallback onToggleFavorite;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final progress = series.readingProgress;

    return GestureDetector(
      onTap: onTap,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 2 / 3,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  SeriesCoverImage(
                    url: seriesCoverUrl(baseUrl, series.id),
                    borderRadius: AppRadius.xl,
                  ),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          Colors.transparent,
                          AppColors.bg.withAlpha(230),
                        ],
                      ),
                    ),
                  ),
                  if (series.readingStatus.isNotEmpty)
                    Positioned(
                      left: AppSpacing.sm,
                      top: AppSpacing.sm,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: readingStatusColor(series.readingStatus)
                              .withAlpha(204),
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Text(
                          readingStatusLabel(series.readingStatus).toUpperCase(),
                          style: AppTypography.caption.copyWith(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ),
                  Positioned(
                    right: AppSpacing.sm,
                    top: AppSpacing.sm,
                    child: _FavoriteButton(
                      isFavorite: series.isFavorite,
                      onPressed: onToggleFavorite,
                    ),
                  ),
                  if (onRemove != null)
                    Positioned(
                      left: AppSpacing.sm,
                      top: AppSpacing.sm,
                      child: _RemoveButton(onPressed: onRemove!),
                    ),
                  Positioned(
                    left: AppSpacing.md,
                    right: AppSpacing.md,
                    bottom: AppSpacing.md,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          series.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: AppTypography.labelLg.copyWith(
                            color: Colors.white,
                            height: 1.2,
                          ),
                        ),
                        Text(
                          '${series.chapterCount} chapters',
                          style: AppTypography.caption.copyWith(
                            color: Colors.white.withAlpha(179),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: _ProgressLabel(
                  series: series,
                  progressPct: progress?.progressPct,
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 6,
                  vertical: 2,
                ),
                decoration: BoxDecoration(
                  color: AppColors.fg.withAlpha(13),
                  borderRadius: BorderRadius.circular(AppRadius.sm),
                ),
                child: Text(
                  languageLabel(series.language).toUpperCase(),
                  style: AppTypography.caption.copyWith(fontSize: 10),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class SeriesListTile extends ConsumerWidget {
  const SeriesListTile({
    super.key,
    required this.series,
    required this.onTap,
    required this.onToggleFavorite,
    this.onRemove,
  });

  final SeriesSummary series;
  final VoidCallback onTap;
  final VoidCallback onToggleFavorite;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final progress = series.readingProgress;

    return GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          SeriesCoverImage(
            url: seriesCoverUrl(baseUrl, series.id),
            width: 64,
            height: 64,
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Wrap(
                  spacing: AppSpacing.sm,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      series.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.labelLg,
                    ),
                    if (series.readingStatus.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: 2,
                        ),
                        decoration: BoxDecoration(
                          color: readingStatusColor(series.readingStatus)
                              .withAlpha(204),
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Text(
                          readingStatusLabel(series.readingStatus).toUpperCase(),
                          style: AppTypography.caption.copyWith(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: Colors.white,
                          ),
                        ),
                      ),
                  ],
                ),
                if (series.author != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    series.author!,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption,
                  ),
                ],
                const SizedBox(height: 4),
                Text(
                  '${series.chapterCount} chapters · ${languageLabel(series.language)}'
                  '${progress != null ? ' · ${progress.progressPct.round()}% read' : ''}',
                  style: AppTypography.caption,
                ),
              ],
            ),
          ),
          _FavoriteButton(
            isFavorite: series.isFavorite,
            onPressed: onToggleFavorite,
            compact: true,
          ),
          if (onRemove != null) ...[
            const SizedBox(width: AppSpacing.sm),
            _RemoveButton(onPressed: onRemove!),
          ],
        ],
      ),
    );
  }
}

class _FavoriteButton extends StatelessWidget {
  const _FavoriteButton({
    required this.isFavorite,
    required this.onPressed,
    this.compact = false,
  });

  final bool isFavorite;
  final VoidCallback onPressed;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bg.withAlpha(128),
      shape: const CircleBorder(),
      child: InkWell(
        onTap: onPressed,
        customBorder: const CircleBorder(),
        child: SizedBox(
          width: compact ? 36 : 32,
          height: compact ? 36 : 32,
          child: Icon(
            isFavorite ? Icons.star : Icons.star_border,
            size: compact ? 20 : 18,
            color: isFavorite ? AppColors.warning : AppColors.fg.withAlpha(179),
          ),
        ),
      ),
    );
  }
}

class _RemoveButton extends StatelessWidget {
  const _RemoveButton({required this.onPressed});

  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.bg.withAlpha(179),
      shape: const CircleBorder(),
      child: InkWell(
        onTap: onPressed,
        customBorder: const CircleBorder(),
        child: const Padding(
          padding: EdgeInsets.all(6),
          child: Icon(
            Icons.remove_circle_outline,
            size: 18,
            color: AppColors.danger,
          ),
        ),
      ),
    );
  }
}

class _ProgressLabel extends StatelessWidget {
  const _ProgressLabel({
    required this.series,
    required this.progressPct,
  });

  final SeriesSummary series;
  final double? progressPct;

  @override
  Widget build(BuildContext context) {
    if (progressPct != null) {
      return Row(
        children: [
          const Icon(Icons.star, size: 12, color: AppColors.warning),
          const SizedBox(width: 4),
          Text(
            '${progressPct!.round()}%',
            style: AppTypography.caption.copyWith(color: AppColors.warning),
          ),
        ],
      );
    }

    if (series.isFavorite) {
      return Row(
        children: [
          const Icon(Icons.star, size: 12, color: AppColors.warning),
          const SizedBox(width: 4),
          Text(
            'Favorite',
            style: AppTypography.caption.copyWith(color: AppColors.warning),
          ),
        ],
      );
    }

    if (series.readChapters > 0) {
      return Text(
        '${series.readChapters}/${series.chapterCount} read',
        style: AppTypography.caption,
      );
    }

    return Text('—', style: AppTypography.caption.copyWith(color: AppColors.muted));
  }
}

class SeriesGrid extends ConsumerWidget {
  const SeriesGrid({
    super.key,
    required this.items,
    required this.viewMode,
    required this.onSeriesTap,
    required this.onToggleFavorite,
    this.onRemoveSeries,
  });

  final List<SeriesSummary> items;
  final LibraryViewMode viewMode;
  final ValueChanged<SeriesSummary> onSeriesTap;
  final ValueChanged<int> onToggleFavorite;
  final ValueChanged<int>? onRemoveSeries;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (viewMode == LibraryViewMode.list) {
      return Column(
        children: [
          for (final series in items) ...[
            SeriesListTile(
              series: series,
              onTap: () => onSeriesTap(series),
              onToggleFavorite: () => onToggleFavorite(series.id),
              onRemove: onRemoveSeries == null ? null : () => onRemoveSeries!(series.id),
            ),
            const SizedBox(height: AppSpacing.md),
          ],
        ],
      );
    }

    final columns = context.seriesGridColumns;

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        crossAxisSpacing: AppSpacing.lg,
        mainAxisSpacing: AppSpacing.lg,
        childAspectRatio: 0.52,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final series = items[index];
        return SeriesCard(
          series: series,
          onTap: () => onSeriesTap(series),
          onToggleFavorite: () => onToggleFavorite(series.id),
          onRemove: onRemoveSeries == null ? null : () => onRemoveSeries!(series.id),
        );
      },
    );
  }
}
