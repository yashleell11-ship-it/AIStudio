import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
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
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  context.colors.void_,
                  context.colors.bg,
                  context.colors.abyss,
                ],
                stops: const [0.0, 0.55, 1.0],
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
                    context.colors.primary.withAlpha(35),
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
                    context.colors.accent.withAlpha(25),
                    Colors.transparent,
                  ],
                ),
              ),
            ),
          ),

          // Bottom fade-to-bg
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            height: 80,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Colors.transparent, context.colors.bg],
                ),
              ),
            ),
          ),

          // Content
          Positioned(
            left: context.space.xl2,
            right: context.space.xl2,
            bottom: context.space.xl3,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                // Brand wordmark
                Text(
                  'MANHWAMANIACS',
                  style: context.text.displayMd.copyWith(
                    fontSize: 13,
                    letterSpacing: 4,
                    color: context.colors.cyan400.withAlpha(180),
                    fontWeight: FontWeight.w700,
                  ),
                ),
                SizedBox(height: context.space.sm),
                Text(
                  'Your manga\ncollection.',
                  style: context.text.displayLg.copyWith(
                    fontSize: 40,
                    height: 1.0,
                    letterSpacing: 0.5,
                    color: context.colors.fg,
                  ),
                ),
                SizedBox(height: context.space.xl2),
                Row(
                  children: [
                    FilledButton.icon(
                      onPressed: onBrowseLibrary,
                      icon: const Icon(Icons.auto_stories_outlined, size: 16),
                      label: const Text('Browse'),
                    ),
                    if (firstContinueItem != null) ...[
                      SizedBox(width: context.space.md),
                      OutlinedButton.icon(
                        onPressed: onContinueReading,
                        icon: const Icon(Icons.play_arrow_rounded, size: 16),
                        label: const Text('Continue'),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: context.colors.fg,
                          side: BorderSide(color: context.colors.border.withAlpha(180)),
                          backgroundColor: context.colors.fg.withAlpha(8),
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
          accentColor: context.colors.cyan400,
        ),
        SizedBox(width: context.space.md),
        _QuickActionButton(
          icon: Icons.download_rounded,
          label: 'Downloads',
          onTap: onDownloads,
          accentColor: context.colors.emerald400,
        ),
        SizedBox(width: context.space.md),
        _QuickActionButton(
          icon: Icons.notifications_rounded,
          label: 'Updates',
          onTap: onUpdates,
          accentColor: context.colors.amber400,
        ),
        SizedBox(width: context.space.md),
        _QuickActionButton(
          icon: Icons.settings_rounded,
          label: 'Settings',
          onTap: onSettings,
          accentColor: context.colors.violet400,
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
        padding: EdgeInsets.symmetric(
          vertical: context.space.xl,
          horizontal: context.space.sm,
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
            SizedBox(height: context.space.sm),
            Text(
              label,
              style: context.text.labelSm.copyWith(
                color: context.colors.muted,
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

  final List<FollowedSeries> series;
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
            padding: EdgeInsets.only(bottom: context.space.xs),
            itemCount: series.length,
            separatorBuilder: (_, __) => SizedBox(width: context.space.lg),
            itemBuilder: (context, index) {
              final item = series[index];
              return _TrendingCoverCard(
                title: item.title,
                coverUrl: followedSeriesCoverUrl(baseUrl, item) ?? '',
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
          borderRadius: BorderRadius.circular(context.radii.xl),
          child: Stack(
            fit: StackFit.expand,
            children: [
              SeriesCoverImage(
                url: coverUrl,
                width: 148,
                height: 220,
                borderRadius: context.radii.xl,
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
                      context.colors.bg.withAlpha(240),
                    ],
                  ),
                ),
              ),
              Positioned(
                left: context.space.md,
                right: context.space.md,
                bottom: context.space.md,
                child: Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: context.text.labelSm.copyWith(
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
            padding: EdgeInsets.only(bottom: context.space.xs),
            itemCount: items.length,
            separatorBuilder: (_, __) => SizedBox(width: context.space.md),
            itemBuilder: (context, index) {
              final item = items[index];
              return _ContinueReadingCard(
                item: item,
                coverUrl: sourceSeriesCoverUrl(baseUrl, item.sourceId, item.seriesKey),
                onTap: () => context.push(
                  RoutePaths.reader(item.sourceId, item.seriesKey, item.chapterKey),
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
    final label = chapterLabel(number: item.chapterNumber, title: null);
    return SizedBox(
      width: 300,
      child: GlassCard(
        onTap: onTap,
        glowColor: context.colors.primary,
        padding: EdgeInsets.all(context.space.lg),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(context.radii.md),
              child: SeriesCoverImage(
                url: coverUrl,
                width: 64,
                height: 88,
              ),
            ),
            SizedBox(width: context.space.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    label.primary,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: context.text.labelLg.copyWith(fontWeight: FontWeight.w600),
                  ),
                  SizedBox(height: context.space.xxs),
                  Text(
                    item.sourceId,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: context.text.caption.copyWith(color: context.colors.muted),
                  ),
                  SizedBox(height: context.space.md),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(context.radii.full),
                    child: LinearProgressIndicator(
                      value: item.progressPct,
                      minHeight: 3,
                      backgroundColor: context.colors.fg.withAlpha(20),
                      color: context.colors.primary,
                    ),
                  ),
                  SizedBox(height: context.space.xs),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Page ${item.lastPage}',
                        style: context.text.caption.copyWith(color: context.colors.muted, fontSize: 10),
                      ),
                      Text(
                        '${(item.progressPct * 100).round()}%',
                        style: context.text.caption.copyWith(
                          fontSize: 10,
                          color: context.colors.primary,
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
      mainAxisSpacing: context.space.lg,
      crossAxisSpacing: context.space.lg,
      childAspectRatio: 1.05,
      children: [
        StatCard(
          icon: Icons.menu_book_outlined,
          value: numberFormat.format(stats.followedTotal),
          label: 'Followed Series',
          accent: StatAccent.violet,
        ),
        StatCard(
          icon: Icons.star_outline,
          value: numberFormat.format(stats.favorites),
          label: 'Favorites',
          accent: StatAccent.amber,
        ),
        StatCard(
          icon: Icons.check_circle_outline,
          value: numberFormat.format(stats.byReadingStatus['completed'] ?? 0),
          label: 'Completed',
          accent: StatAccent.emerald,
        ),
        StatCard(
          icon: Icons.auto_stories_outlined,
          value: numberFormat.format(stats.chaptersCompleted),
          label: 'Chapters Read',
          accent: StatAccent.cyan,
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
      padding: EdgeInsets.only(bottom: context.space.xl3),
      children: [
        const SizedBox(height: 240),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: context.space.xl2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SkeletonBox(width: double.infinity, height: 80),
              SizedBox(height: context.space.xl3),
              const SkeletonBox(width: 160, height: 16),
              SizedBox(height: context.space.lg),
              SizedBox(
                height: 220,
                child: Row(
                  children: [
                    const SkeletonBox(width: 148, height: 220, borderRadius: 20),
                    SizedBox(width: context.space.lg),
                    const SkeletonBox(width: 148, height: 220, borderRadius: 20),
                    SizedBox(width: context.space.lg),
                    const SkeletonBox(width: 148, height: 220, borderRadius: 20),
                  ],
                ),
              ),
              SizedBox(height: context.space.xl3),
              Row(
                children: [
                  const Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                  SizedBox(width: context.space.lg),
                  const Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                ],
              ),
              SizedBox(height: context.space.lg),
              Row(
                children: [
                  const Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                  SizedBox(width: context.space.lg),
                  const Expanded(child: SkeletonBox(width: double.infinity, height: 130)),
                ],
              ),
              SizedBox(height: context.space.xl3),
              const SkeletonBox(width: 180, height: 16),
              SizedBox(height: context.space.lg),
              const SkeletonBox(width: double.infinity, height: 120),
              SizedBox(height: context.space.xl3),
              const SkeletonBox(width: 180, height: 16),
              SizedBox(height: context.space.lg),
              const SkeletonBox(width: double.infinity, height: 64),
              SizedBox(height: context.space.sm),
              const SkeletonBox(width: double.infinity, height: 64),
            ],
          ),
        ),
      ],
    );
  }
}