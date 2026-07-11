import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';
import 'package:manhwamaniacs/shared/widgets/stat_card.dart';

class StatisticsScreen extends ConsumerWidget {
  const StatisticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statsAsync = ref.watch(statisticsProvider);
    final numberFormat = NumberFormat.decimalPattern();

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        title: const Text('Statistics'),
      ),
      body: statsAsync.when(
        loading: () => GridView.count(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          crossAxisCount: 2,
          mainAxisSpacing: AppSpacing.md,
          crossAxisSpacing: AppSpacing.md,
          children: List.generate(8, (_) => const SkeletonBox(width: double.infinity, height: 90)),
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load statistics.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(statisticsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (stats) => RefreshIndicator(
          color: AppColors.primary,
          onRefresh: () async => ref.invalidate(statisticsProvider),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              Text('Reading Statistics', style: AppTypography.displayMd),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Your library and reading activity at a glance.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              GridView.count(
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
                    label: 'Total Series',
                    accent: StatAccent.violet,
                  ),
                  StatCard(
                    icon: Icons.schedule,
                    value: numberFormat.format(stats.totalChapters),
                    label: 'Total Chapters',
                    accent: StatAccent.cyan,
                  ),
                  StatCard(
                    icon: Icons.storage_outlined,
                    value: numberFormat.format(stats.totalPages),
                    label: 'Total Pages',
                    accent: StatAccent.amber,
                  ),
                  StatCard(
                    icon: Icons.check_circle_outline,
                    value: '${stats.completedSeries}',
                    label: 'Completed',
                    accent: StatAccent.emerald,
                  ),
                  StatCard(
                    icon: Icons.play_circle_outline,
                    value: '${stats.inProgress}',
                    label: 'In Progress',
                    accent: StatAccent.cyan,
                  ),
                  StatCard(
                    icon: Icons.star_outline,
                    value: '${stats.favorites}',
                    label: 'Favorites',
                    accent: StatAccent.amber,
                  ),
                  StatCard(
                    icon: Icons.local_fire_department_outlined,
                    value: '${stats.readingStreakDays} days',
                    label: 'Reading Streak',
                    accent: StatAccent.emerald,
                  ),
                  StatCard(
                    icon: Icons.calendar_today_outlined,
                    value: '${stats.pagesReadThisWeek}',
                    label: 'Pages This Week',
                    accent: StatAccent.violet,
                  ),
                  StatCard(
                    icon: Icons.speed_outlined,
                    value: stats.readingVelocityPagesPerHour > 0
                        ? numberFormat
                            .format(stats.readingVelocityPagesPerHour.round())
                        : '—',
                    label: 'Pages / Hour',
                    accent: StatAccent.cyan,
                  ),
                  StatCard(
                    icon: Icons.hourglass_bottom_outlined,
                    value: _formatReadingTime(
                      stats.totalReadingTimeEstimateMinutes,
                    ),
                    label: 'Time Read',
                    accent: StatAccent.amber,
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.xl2),
              _CompletionCard(stats: stats),
              if (stats.weeklyChart.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                _WeeklyChartCard(stats: stats),
              ],
              if (stats.topAuthors.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                _TopAuthorsCard(stats: stats),
              ],
              if (stats.tagDistribution.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                _TopTagsCard(stats: stats),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Formats a reading-time estimate (minutes) into a compact "Xh Ym" / "Xm".
String _formatReadingTime(int minutes) {
  if (minutes <= 0) return '—';
  if (minutes < 60) return '${minutes}m';
  final hours = minutes ~/ 60;
  final rem = minutes % 60;
  return rem == 0 ? '${hours}h' : '${hours}h ${rem}m';
}

class _CompletionCard extends StatelessWidget {
  const _CompletionCard({required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Completion Rate', style: AppTypography.h4),
          const SizedBox(height: AppSpacing.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('${stats.completionRatePct}%', style: AppTypography.labelLg),
              Text(
                '${stats.completedSeries} / ${stats.totalSeries} series',
                style: AppTypography.caption.copyWith(color: AppColors.muted),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          LinearProgressIndicator(value: stats.completionRatePct / 100),
        ],
      ),
    );
  }
}

class _WeeklyChartCard extends StatelessWidget {
  const _WeeklyChartCard({required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    final maxPages = stats.weeklyChart
        .map((item) => item.pagesRead)
        .fold<int>(0, (max, value) => value > max ? value : max);

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Weekly Activity', style: AppTypography.h4),
          const SizedBox(height: AppSpacing.lg),
          SizedBox(
            height: 120,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                for (final item in stats.weeklyChart) ...[
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 2),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Text('${item.pagesRead}', style: AppTypography.caption),
                          const SizedBox(height: 4),
                          Expanded(
                            child: Align(
                              alignment: Alignment.bottomCenter,
                              child: FractionallySizedBox(
                                heightFactor: maxPages == 0 ? 0 : item.pagesRead / maxPages,
                                child: Container(
                                  width: double.infinity,
                                  decoration: BoxDecoration(
                                    color: AppColors.primary.withAlpha(179),
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(item.label, style: AppTypography.caption),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TopAuthorsCard extends StatelessWidget {
  const _TopAuthorsCard({required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Top Authors', style: AppTypography.h4),
          const SizedBox(height: AppSpacing.md),
          for (final author in stats.topAuthors.take(8))
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Row(
                children: [
                  Expanded(child: Text(author.author, style: AppTypography.body)),
                  Text(
                    '${author.seriesCount} series',
                    style: AppTypography.caption.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _TopTagsCard extends StatelessWidget {
  const _TopTagsCard({required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Top Tags', style: AppTypography.h4),
          const SizedBox(height: AppSpacing.md),
          Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.sm,
            children: [
              for (final tag in stats.tagDistribution.take(12))
                Chip(label: Text('${tag.name} (${tag.seriesCount})')),
            ],
          ),
        ],
      ),
    );
  }
}