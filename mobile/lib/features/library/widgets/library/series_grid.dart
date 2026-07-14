import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/utils/responsive.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

class SeriesCard extends ConsumerWidget {
  const SeriesCard({
    super.key,
    required this.series,
    required this.onTap,
    required this.onToggleFavorite,
    this.onRemove,
    this.onLongPress,
    this.selectionMode = false,
    this.selected = false,
  });

  final SeriesSummary series;
  final VoidCallback onTap;
  final VoidCallback onToggleFavorite;
  final VoidCallback? onRemove;
  final VoidCallback? onLongPress;

  /// Whether the library is in multi-select mode. When true, every card
  /// shows a checkbox circle instead of its usual favorite/remove buttons.
  final bool selectionMode;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final progress = series.readingProgress;

    return Pressable(
      onTap: onTap,
      onLongPress: onLongPress,
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
                  Hero(
                    tag: seriesCoverHeroTag(series.id),
                    child: SeriesCoverImage(
                      url: seriesCoverUrl(baseUrl, series.id),
                      borderRadius: AppRadius.xl,
                    ),
                  ),
                  if (selected)
                    DecoratedBox(
                      decoration: BoxDecoration(
                        color: AppColors.primary.withAlpha(60),
                        border: Border.all(color: AppColors.primary, width: 3),
                        borderRadius: BorderRadius.circular(AppRadius.xl),
                      ),
                    ),
                  // Bottom gradient for text legibility
                  Positioned(
                    left: 0,
                    right: 0,
                    bottom: 0,
                    height: 110,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            Colors.transparent,
                            AppColors.bg.withAlpha(240),
                          ],
                        ),
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
                          vertical: AppSpacing.xxs,
                        ),
                        decoration: BoxDecoration(
                          color: readingStatusColor(series.readingStatus)
                              .withAlpha(220),
                          borderRadius: BorderRadius.circular(AppRadius.sm),
                        ),
                        child: Text(
                          readingStatusLabel(series.readingStatus).toUpperCase(),
                          style: AppTypography.caption.copyWith(
                            fontSize: 9,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                            letterSpacing: 0.6,
                          ),
                        ),
                      ),
                    ),
                  if (selectionMode)
                    Positioned(
                      right: AppSpacing.xs,
                      top: AppSpacing.xs,
                      child: _SelectionCheckbox(selected: selected),
                    )
                  else ...[
                    Positioned(
                      right: AppSpacing.xs,
                      top: AppSpacing.xs,
                      child: _FavoriteButton(
                        isFavorite: series.isFavorite,
                        onPressed: onToggleFavorite,
                      ),
                    ),
                    if (onRemove != null)
                      Positioned(
                        left: AppSpacing.xs,
                        top: AppSpacing.xs,
                        child: _RemoveButton(onPressed: onRemove!),
                      ),
                  ],
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
                          style: AppTypography.label.copyWith(
                            color: Colors.white,
                            height: 1.2,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: AppSpacing.xxs),
                        Text(
                          '${series.chapterCount} ch',
                          style: AppTypography.caption.copyWith(
                            color: Colors.white.withAlpha(160),
                            fontSize: 10,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          _ProgressLabel(
            series: series,
            progressPct: progress?.progressPct,
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
    this.onLongPress,
    this.selectionMode = false,
    this.selected = false,
  });

  final SeriesSummary series;
  final VoidCallback onTap;
  final VoidCallback onToggleFavorite;
  final VoidCallback? onRemove;
  final VoidCallback? onLongPress;
  final bool selectionMode;
  final bool selected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final progress = series.readingProgress;

    return GestureDetector(
      onLongPress: onLongPress,
      child: GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Row(
        children: [
          Hero(
            tag: seriesCoverHeroTag(series.id),
            child: SeriesCoverImage(
              url: seriesCoverUrl(baseUrl, series.id),
              width: 64,
              height: 64,
            ),
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
          if (selectionMode)
            _SelectionCheckbox(selected: selected)
          else ...[
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
        ],
      ),
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

/// Selection-mode checkbox circle. The whole card's `onTap` toggles it
/// (wired by the parent screen), so this is purely a visual indicator, not
/// an interactive widget itself.
class _SelectionCheckbox extends StatelessWidget {
  const _SelectionCheckbox({required this.selected});

  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 26,
      height: 26,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected ? AppColors.primary : AppColors.bg.withAlpha(150),
        border: Border.all(
          color: selected ? AppColors.primary : AppColors.fg.withAlpha(150),
          width: 1.5,
        ),
      ),
      child: selected
          ? const Icon(Icons.check, size: 16, color: Colors.white)
          : null,
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
    this.onSeriesLongPress,
    this.coverScale = 1.0,
    this.selectionMode = false,
    this.selectedIds = const {},
  });

  final List<SeriesSummary> items;
  final LibraryViewMode viewMode;
  final ValueChanged<SeriesSummary> onSeriesTap;
  final ValueChanged<int> onToggleFavorite;
  final ValueChanged<int>? onRemoveSeries;
  final ValueChanged<SeriesSummary>? onSeriesLongPress;

  /// Cover-size multiplier; higher = larger covers / fewer columns.
  final double coverScale;

  /// Library multi-select: shows a checkbox on every card instead of the
  /// usual favorite/remove buttons when true.
  final bool selectionMode;
  final Set<int> selectedIds;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (viewMode == LibraryViewMode.list) {
      return Column(
        children: [
          for (var i = 0; i < items.length; i++) ...[
            ScrollReveal(
              index: i,
              child: SeriesListTile(
                series: items[i],
                onTap: () => onSeriesTap(items[i]),
                onToggleFavorite: () => onToggleFavorite(items[i].id),
                onLongPress: onSeriesLongPress == null
                    ? null
                    : () => onSeriesLongPress!(items[i]),
                onRemove: onRemoveSeries == null
                    ? null
                    : () => onRemoveSeries!(items[i].id),
                selectionMode: selectionMode,
                selected: selectedIds.contains(items[i].id),
              ),
            ),
            const SizedBox(height: AppSpacing.md),
          ],
        ],
      );
    }

    // Fewer columns as covers scale up; clamp to a sensible range.
    final base = context.seriesGridColumns;
    final columns = (base / coverScale).round().clamp(2, 6);

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        crossAxisSpacing: AppSpacing.md,
        mainAxisSpacing: AppSpacing.xl,
        childAspectRatio: 0.52,
      ),
      itemCount: items.length,
      itemBuilder: (context, index) {
        final series = items[index];
        return ScrollReveal(
          index: index,
          child: SeriesCard(
            series: series,
            onTap: () => onSeriesTap(series),
            onToggleFavorite: () => onToggleFavorite(series.id),
            onLongPress: onSeriesLongPress == null
                ? null
                : () => onSeriesLongPress!(series),
            onRemove: onRemoveSeries == null ? null : () => onRemoveSeries!(series.id),
            selectionMode: selectionMode,
            selected: selectedIds.contains(series.id),
          ),
        );
      },
    );
  }
}