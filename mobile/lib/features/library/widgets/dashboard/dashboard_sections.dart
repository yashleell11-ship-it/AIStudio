import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/library_statistics.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/utils/cover_url.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/section_header.dart';
import 'package:aistudio_mobile/shared/widgets/series_cover_image.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
import 'package:aistudio_mobile/shared/widgets/stat_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

class DashboardHero extends StatelessWidget {
  const DashboardHero({
    super.key,
    this.firstContinueItem,
    required this.onBrowseLibrary,
    required this.onContinueReading,
  });

  final ContinueReadingItem? firstContinueItem;
  final VoidCallback onBrowseLibrary;
  final VoidCallback onContinueReading;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.primary.withAlpha(26),
                  Colors.transparent,
                ],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: Center(
            child: Text(
              'AIStudio',
              style: AppTypography.displayLg.copyWith(
                fontSize: 96,
                color: AppColors.fg.withAlpha(8),
              ),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            AppSpacing.xl4,
            AppSpacing.xl2,
            AppSpacing.xl2,
          ),
          child: Column(
            children: [
              Text(
                'AIStudio',
                style: AppTypography.displayMd,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.md),
              Text(
                'Your Premium Manga & Webtoon Experience',
                style: AppTypography.body.copyWith(color: AppColors.muted),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: AppSpacing.xl2),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: AppSpacing.md,
                runSpacing: AppSpacing.md,
                children: [
                  FilledButton(
                    onPressed: onBrowseLibrary,
                    child: const Text('Browse Library'),
                  ),
                  if (firstContinueItem != null)
                    OutlinedButton.icon(
                      onPressed: onContinueReading,
                      icon: const Icon(Icons.play_arrow, size: 18),
                      label: const Text('Continue Reading'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.fg,
                        side: BorderSide(color: AppColors.border.withAlpha(128)),
                        backgroundColor: AppColors.fg.withAlpha(13),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class QuickActionsRow extends StatelessWidget {
  const QuickActionsRow({
    super.key,
    required this.onSearch,
    required this.onDownloads,
    required this.onUpdates,
    required this.onSettings,
  });

  final VoidCallback onSearch;
  final VoidCallback onDownloads;
  final VoidCallback onUpdates;
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _QuickActionButton(
            icon: Icons.search,
            label: 'Search',
            onTap: onSearch,
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: _QuickActionButton(
            icon: Icons.download_outlined,
            label: 'Downloads',
            onTap: onDownloads,
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: _QuickActionButton(
            icon: Icons.notifications_outlined,
            label: 'Updates',
            onTap: onUpdates,
          ),
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: _QuickActionButton(
            icon: Icons.settings_outlined,
            label: 'Settings',
            onTap: onSettings,
          ),
        ),
      ],
    );
  }
}

class _QuickActionButton extends StatelessWidget {
  const _QuickActionButton({
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      onTap: onTap,
      padding: const EdgeInsets.symmetric(
        vertical: AppSpacing.lg,
        horizontal: AppSpacing.sm,
      ),
      child: Column(
        children: [
          Icon(icon, color: AppColors.cyan400, size: 22),
          const SizedBox(height: AppSpacing.sm),
          Text(
            label,
            style: AppTypography.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class RecentlyUpdatedCarousel extends ConsumerWidget {
  const RecentlyUpdatedCarousel({
    super.key,
    required this.series,
    this.onViewAll,
  });

  final List<SeriesSummary> series;
  final VoidCallback? onViewAll;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          icon: Icons.trending_up,
          title: 'Recently Updated',
          onViewAll: onViewAll,
        ),
        SizedBox(
          height: 210,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            itemCount: series.length,
            separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.lg),
            itemBuilder: (context, index) {
              final item = series[index];
              return _TrendingCoverCard(
                title: item.title,
                coverUrl: seriesCoverUrl(baseUrl, item.id),
                onTap: () => context.push(RoutePaths.seriesDetail(item.id)),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _TrendingCoverCard extends StatelessWidget {
  const _TrendingCoverCard({
    required this.title,
    required this.coverUrl,
    required this.onTap,
  });

  final String title;
  final String coverUrl;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 140,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.xl),
          child: Stack(
            fit: StackFit.expand,
            children: [
              SeriesCoverImage(
                url: coverUrl,
                width: 140,
                height: 210,
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
              Positioned(
                left: AppSpacing.sm,
                right: AppSpacing.sm,
                bottom: AppSpacing.sm,
                child: Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.labelSm.copyWith(color: Colors.white),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ContinueReadingSection extends ConsumerWidget {
  const ContinueReadingSection({
    super.key,
    required this.items,
    this.onViewAll,
  });

  final List<ContinueReadingItem> items;
  final VoidCallback? onViewAll;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (items.isEmpty) return const SizedBox.shrink();

    final baseUrl = ref.watch(apiBaseUrlProvider);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          icon: Icons.play_arrow,
          title: 'Continue Reading',
          onViewAll: onViewAll,
        ),
        SizedBox(
          height: 114,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            itemCount: items.length,
            separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.md),
            itemBuilder: (context, index) {
              final item = items[index];
              return _ContinueReadingCard(
                item: item,
                coverUrl: seriesCoverUrl(baseUrl, item.seriesId),
                onTap: () => context.push(
                  '${RoutePaths.seriesDetail(item.seriesId)}/chapters/${item.chapterId}/read',
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _ContinueReadingCard extends StatelessWidget {
  const _ContinueReadingCard({
    required this.item,
    required this.coverUrl,
    required this.onTap,
  });

  final ContinueReadingItem item;
  final String coverUrl;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 280,
      child: GlassCard(
        onTap: onTap,
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            SeriesCoverImage(
              url: coverUrl,
              width: 60,
              height: 90,
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    item.seriesTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    item.chapterTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption,
                  ),
                  const SizedBox(height: AppSpacing.sm),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppRadius.full),
                    child: LinearProgressIndicator(
                      value: item.progressPct / 100,
                      minHeight: 4,
                      backgroundColor: AppColors.fg.withAlpha(26),
                      color: AppColors.cyan500,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Page ${item.lastPage}',
                        style: AppTypography.caption.copyWith(fontSize: 10),
                      ),
                      Text(
                        '${item.progressPct.round()}%',
                        style: AppTypography.caption.copyWith(
                          fontSize: 10,
                          color: AppColors.cyan400,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class StatsGrid extends StatelessWidget {
  const StatsGrid({super.key, required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    final numberFormat = NumberFormat.decimalPattern();

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: AppSpacing.md,
      crossAxisSpacing: AppSpacing.md,
      childAspectRatio: 1.45,
      children: [
        StatCard(
          icon: Icons.menu_book_outlined,
          value: numberFormat.format(stats.totalSeries),
          label: 'Total Comics',
          accent: StatAccent.violet,
        ),
        StatCard(
          icon: Icons.schedule,
          value: numberFormat.format(stats.totalChapters),
          label: 'Total Chapters',
          accent: StatAccent.cyan,
        ),
        StatCard(
          icon: Icons.trending_up,
          value: '${stats.readingStreakDays} days',
          label: 'Reading Streak',
          accent: StatAccent.emerald,
        ),
        StatCard(
          icon: Icons.storage_outlined,
          value: numberFormat.format(stats.totalPages),
          label: 'Total Pages',
          accent: StatAccent.amber,
        ),
      ],
    );
  }
}

class DashboardSkeleton extends StatelessWidget {
  const DashboardSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.only(bottom: AppSpacing.xl3),
      children: const [
        SizedBox(height: 180),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonBox(width: double.infinity, height: 72),
              SizedBox(height: AppSpacing.xl2),
              SkeletonBox(width: 160, height: 16),
              SizedBox(height: AppSpacing.lg),
              SizedBox(
                height: 210,
                child: Row(
                  children: [
                    SkeletonBox(width: 140, height: 210, borderRadius: 16),
                    SizedBox(width: AppSpacing.lg),
                    SkeletonBox(width: 140, height: 210, borderRadius: 16),
                    SizedBox(width: AppSpacing.lg),
                    SkeletonBox(width: 140, height: 210, borderRadius: 16),
                  ],
                ),
              ),
              SizedBox(height: AppSpacing.xl3),
              Row(
                children: [
                  Expanded(child: SkeletonBox(width: double.infinity, height: 108)),
                  SizedBox(width: AppSpacing.md),
                  Expanded(child: SkeletonBox(width: double.infinity, height: 108)),
                ],
              ),
              SizedBox(height: AppSpacing.md),
              Row(
                children: [
                  Expanded(child: SkeletonBox(width: double.infinity, height: 108)),
                  SizedBox(width: AppSpacing.md),
                  Expanded(child: SkeletonBox(width: double.infinity, height: 108)),
                ],
              ),
              SizedBox(height: AppSpacing.xl3),
              SkeletonBox(width: 180, height: 16),
              SizedBox(height: AppSpacing.lg),
              SkeletonBox(width: double.infinity, height: 114),
              SizedBox(height: AppSpacing.xl3),
              SkeletonBox(width: 180, height: 16),
              SizedBox(height: AppSpacing.lg),
              SkeletonBox(width: double.infinity, height: 64),
              SizedBox(height: AppSpacing.sm),
              SkeletonBox(width: double.infinity, height: 64),
            ],
          ),
        ),
      ],
    );
  }
}
