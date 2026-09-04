import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/widgets/statistics/statistics_sections.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/section_header.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Reading statistics — source-native (`GET /library/statistics`).
///
/// The payload has two halves and the screen forks on which of them exist:
/// the library shape (followed/favorites/status/chapters finished) is always
/// real, while everything session-derived — streak, daily activity, reading
/// clock, per-source and per-series breakdowns — only exists once
/// `reading_sessions` rows have been recorded. A profile with no recorded
/// reading gets told how the numbers get built instead of a wall of zeroes;
/// see `widgets/statistics/statistics_sections.dart` for each section's own
/// sparse-data reasoning.
class StatisticsScreen extends ConsumerWidget {
  const StatisticsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statsAsync = ref.watch(statisticsProvider);
    final scope = ref.watch(contentModeScopeProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        title: const Text('Statistics'),
      ),
      body: statsAsync.when(
        loading: () => const _StatisticsSkeleton(),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load statistics.',
                style: AppTypography.body.copyWith(color: context.colors.danger),
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
          color: context.colors.primary,
          onRefresh: () async => ref.invalidate(statisticsProvider),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              const HeroHeading(text: 'Reading Statistics'),
              const SizedBox(height: AppSpacing.xs),
              Text(
                stats.hasReadingHistory
                    ? 'Built from every chapter you read in the app.'
                    : 'Your library at a glance.',
                style: AppTypography.body.copyWith(color: context.colors.muted),
              ),
              // The breakdowns below carry a source id and are scoped to the
              // active mode. The all-time totals, the streak and the clock are
              // computed server-side across everything read and cannot be
              // split here, so the line says so rather than letting a
              // combined number sit under a "Novels" app.
              if (scope.novelsEnabled && stats.hasReadingHistory)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.xs),
                  child: Text(
                    'Streak, totals and the clock cover everything you read; '
                    'the breakdowns below are '
                    '${scope.isNovel ? 'novels' : 'manga'} only.',
                    style: AppTypography.caption
                        .copyWith(color: context.colors.muted),
                  ),
                ),
              const SizedBox(height: AppSpacing.xl2),
              if (!stats.hasReadingHistory) ...[
                NoReadingHistoryCard(followedTotal: stats.followedTotal),
                const SizedBox(height: AppSpacing.xl2),
              ] else ...[
                StreakCard(stats: stats),
                const SizedBox(height: AppSpacing.md),
                ActivityCard(stats: stats),
                // The clock plots the same window as the activity chart, so
                // it follows it directly and shares its emptiness: a window
                // with nothing read would draw 24 floor ticks and no insight.
                if (stats.hasWindowActivity) ...[
                  const SizedBox(height: AppSpacing.md),
                  ReadingClockCard(byHour: stats.byHour),
                ],
                const SizedBox(height: AppSpacing.xl2),
                const SectionHeader(
                  icon: Icons.query_stats_outlined,
                  title: 'All-Time Reading',
                ),
                ReadingTotalsGrid(totals: stats.totals),
                const SizedBox(height: AppSpacing.xl2),
                if (scope.filter(stats.bySource, (s) => s.sourceId)
                    case final bySource when bySource.isNotEmpty) ...[
                  SourceBreakdownCard(sources: bySource),
                  const SizedBox(height: AppSpacing.xl2),
                ],
                if (scope.filter(stats.bySeries, (s) => s.sourceId)
                    case final bySeries when bySeries.isNotEmpty) ...[
                  TopSeriesSection(series: bySeries),
                  const SizedBox(height: AppSpacing.lg),
                ],
                if (scope.filter(stats.recentSessions, (s) => s.sourceId)
                    case final sessions when sessions.isNotEmpty) ...[
                  RecentSessionsSection(sessions: sessions),
                  const SizedBox(height: AppSpacing.xl2),
                ],
              ],
              const SectionHeader(
                icon: Icons.collections_bookmark_outlined,
                title: 'Your Library',
              ),
              LibraryShapeGrid(stats: stats),
              if (stats.byReadingStatus.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.md),
                ReadingStatusCard(byReadingStatus: stats.byReadingStatus),
              ],
              const SizedBox(height: AppSpacing.xl3),
            ],
          ),
        ),
      ),
    );
  }
}

/// Loading placeholder shaped like the loaded screen — a heading, a streak
/// card, the activity chart, then a grid — so the load doesn't reflow.
class _StatisticsSkeleton extends StatelessWidget {
  const _StatisticsSkeleton();

  @override
  Widget build(BuildContext context) {
    return ListView(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: [
        const SkeletonBox(width: 220, height: 30),
        const SizedBox(height: AppSpacing.md),
        const SkeletonBox(width: 160, height: 14),
        const SizedBox(height: AppSpacing.xl2),
        const SkeletonBox(width: double.infinity, height: 140),
        const SizedBox(height: AppSpacing.md),
        const SkeletonBox(width: double.infinity, height: 220),
        const SizedBox(height: AppSpacing.xl2),
        for (var row = 0; row < 2; row++) ...[
          const Row(
            children: [
              Expanded(child: SkeletonBox(width: double.infinity, height: 90)),
              SizedBox(width: AppSpacing.md),
              Expanded(child: SkeletonBox(width: double.infinity, height: 90)),
            ],
          ),
          if (row == 0) const SizedBox(height: AppSpacing.md),
        ],
      ],
    );
  }
}
