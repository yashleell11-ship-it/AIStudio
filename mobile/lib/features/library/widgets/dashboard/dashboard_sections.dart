import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/section_header.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';
import 'package:manhwamaniacs/shared/widgets/stat_card.dart';

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
    final topPad = MediaQuery.paddingOf(context).top;

    return SizedBox(
      height: 240 + topPad,
      child: Stack(
        fit: StackFit.expand,
        children: [
          // Deep gradient background
          const DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  AppColors.void_,
                  AppColors.bg,
                  AppColors.abyss,
                ],
                stops: [0.0, 0.55, 1.0],
              ),
            ),
          ),

          // Radial violet glow (top-left)
          Positioned(
            top: -60,
            left: -60,
            child: Container(
              width: 280,
              height: 280,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    AppColors.primary.withAlpha(35),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),

          // Radial cyan glow (bottom-right)
          Positioned(
            bottom: -40,
            right: -40,
            child: Container(
              width: 200,
              height: 200,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    AppColors.accent.withAlpha(25),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),

          // Bottom fade-to-bg
          const Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 80,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, AppColors.bg],
                ),
              ),
            ),
          ),

          // Content
          Positioned(
            left: AppSpacing.xl2,
            right: AppSpacing.xl2,
            bottom: AppSpacing.xl3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                // Brand wordmark
                Text(
                  'MANHWAMANIACS',
                  style: AppTypography.displayMd.copyWith(
                    fontSize: 13,
                    letterSpacing: 4,
                    color: AppColors.cyan400.withAlpha(180),
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Your manga\ncollection.',
                  style: AppTypography.displayLg.copyWith(
                    fontSize: 40,
                    height: 1.0,
                    letterSpacing: 0.5,
                    color: AppColors.fg,
                  ),
                ),
                const SizedBox(height: AppSpacing.xl2),
                Row(
                  children: [
                    FilledButton.icon(
                      onPressed: onBrowseLibrary,
                      icon: const Icon(Icons.auto_stories_outlined, size: 16),
                      label: const Text('Browse'),
                    ),
                    if (firstContinueItem != null) ...[
                      const SizedBox(width: AppSpacing.md),
                      OutlinedButton.icon(
                        onPressed: onContinueReading,
                        icon: const Icon(Icons.play_arrow_rounded, size: 16),
                        label: const Text('Continue'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: AppColors.fg,
                          side: BorderSide(color: AppColors.border.withAlpha(180)),
                          backgroundColor: AppColors.fg.withAlpha(8),
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
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
        _QuickActionButton(
          icon: Icons.search_rounded,
          label: 'Search',
          onTap: onSearch,
          accentColor: AppColors.cyan400,
        ),
        const SizedBox(width: AppSpacing.md),
        _QuickActionButton(
          icon: Icons.download_rounded,
          label: 'Downloads',
          onTap: onDownloads,
          accentColor: AppColors.emerald400,
        ),
        const SizedBox(width: AppSpacing.md),
        _QuickActionButton(
          icon: Icons.notifications_rounded,
          label: 'Updates',
          onTap: onUpdates,
          accentColor: AppColors.amber400,
        ),
        const SizedBox(width: AppSpacing.md),
        _QuickActionButton(
          icon: Icons.settings_rounded,
          label: 'Settings',
          onTap: onSettings,
          accentColor: AppColors.violet400,
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
    required this.accentColor,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GlassCard(
        onTap: onTap,
        glowColor: accentColor,
        padding: const EdgeInsets.symmetric(
          vertical: AppSpacing.xl,
          horizontal: AppSpacing.sm,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: RadialGradient(
                  colors: [
                    accentColor.withAlpha(50),
                    accentColor.withAlpha(10),
                  ],
                ),
                border: Border.all(color: accentColor.withAlpha(60)),
              ),
              child: Icon(icon, color: accentColor, size: 20),
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              label,
              style: AppTypography.labelSm.copyWith(
                color: AppColors.muted,
                fontWeight: FontWeight.w600,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
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
          icon: Icons.trending_up_rounded,
          title: 'Recently Updated',
          onViewAll: onViewAll,
        ),
        SizedBox(
          height: 220,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            clipBehavior: Clip.none,
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
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
        width: 148,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.xl),
          child: Stack(
            fit: StackFit.expand,
            children: [
              SeriesCoverImage(
                url: coverUrl,
                width: 148,
                height: 220,
                borderRadius: AppRadius.xl,
              ),
              // Gradient overlay
              DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    stops: const [0.45, 1.0],
                    colors: [
                      Colors.transparent,
                      AppColors.bg.withAlpha(240),
                    ],
                  ),
                ),
              ),
              Positioned(
                left: AppSpacing.md,
                right: AppSpacing.md,
                bottom: AppSpacing.md,
                child: Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: AppTypography.labelSm.copyWith(
                    color: Colors.white,
                    height: 1.3,
                    fontWeight: FontWeight.w600,
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
          icon: Icons.play_arrow_rounded,
          title: 'Continue Reading',
          onViewAll: onViewAll,
        ),
        SizedBox(
          height: 120,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            clipBehavior: Clip.none,
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
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
      width: 300,
      child: GlassCard(
        onTap: onTap,
        glowColor: AppColors.primary,
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(AppRadius.md),
              child: SeriesCoverImage(
                url: coverUrl,
                width: 64,
                height: 88,
              ),
            ),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    item.seriesTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: AppSpacing.xxs),
                  Text(
                    item.chapterTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.caption,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(AppRadius.full),
                    child: LinearProgressIndicator(
                      value: item.progressPct / 100,
                      minHeight: 3,
                      backgroundColor: AppColors.fg.withAlpha(20),
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(height: AppSpacing.xs),
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
                          color: AppColors.primary,
                          fontWeight: FontWeight.w600,
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
      mainAxisSpacing: AppSpacing.lg,
      crossAxisSpacing: AppSpacing.lg,
      childAspectRatio: 1.05,
      children: [
        StatCard(
          icon: Icons.menu_book_outlined,
          value: numberFormat.format(stats.totalSeries),
          label: 'Total Comics',
          accent: StatAccent.violet,
        ),
        StatCard(
          icon: Icons.format_list_numbered,
          value: numberFormat.format(stats.totalChapters),
          label: 'Chapters',
          accent: StatAccent.cyan,
        ),
        StatCard(
          icon: Icons.check_circle_outline,
          value: numberFormat.format(stats.completedSeries),
          label: 'Completed',
          accent: StatAccent.emerald,
        ),
        StatCard(
          icon: Icons.auto_stories_outlined,
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
        SizedBox(height: 240),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SkeletonBox(width: double.infinity, height: 80),
              SizedBox(height: AppSpacing.xl3),
              SkeletonBox(width: 160, height: 16),
              SizedBox(height: AppSpacing.lg),
              SizedBox(
                height: 220,
                child: Row(
                  children: [
                    SkeletonBox(width: 148, height: 220, borderRadius: 20),
                    SizedBox(width: AppSpacing.lg),
                    SkeletonBox(width: 148, height: 220, borderRadius: 20),
                    SizedBox(width: AppSpacing.lg),
                    SkeletonBox(width: 148, height: 220, borderRadius: 20),
                  ],
                ),
              ),
              SizedBox(height: AppSpacing.xl3),
              Row(
                children: [
                  Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                  SizedBox(width: AppSpacing.lg),
                  Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                ],
              ),
              SizedBox(height: AppSpacing.lg),
              Row(
                children: [
                  Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                  SizedBox(width: AppSpacing.lg),
                  Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                ],
              ),
              SizedBox(height: AppSpacing.xl3),
              SkeletonBox(width: 180, height: 16),
              SizedBox(height: AppSpacing.lg),
              SkeletonBox(width: double.infinity, height: 120),
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