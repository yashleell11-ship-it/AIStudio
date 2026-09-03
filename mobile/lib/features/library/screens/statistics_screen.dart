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
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';
import 'package:manhwamaniacs/shared/widgets/stat_card.dart';

/// Reading statistics — source-native (`GET /library/statistics`).
///
/// The backend has no local catalog to draw pages/reading-streak/velocity
/// numbers from any more (`FollowedSeriesService.statistics`), so this screen
/// only states what it can back up: how many series are followed, how many
/// are favorited, the reading-status breakdown, and chapters completed.
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
          children: List.generate(4, (_) => const SkeletonBox(width: double.infinity, height: 90)),
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
              const HeroHeading(text: 'Reading Statistics'),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Your library at a glance.',
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
                    value: numberFormat.format(stats.followedTotal),
                    label: 'Followed Series',
                    accent: StatAccent.amber,
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
                    accent: StatAccent.emerald,
                  ),
                ],
              ),
              if (stats.byReadingStatus.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.xl2),
                _ReadingStatusCard(stats: stats),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ReadingStatusCard extends StatelessWidget {
  const _ReadingStatusCard({required this.stats});

  final LibraryStatistics stats;

  @override
  Widget build(BuildContext context) {
    final entries = stats.byReadingStatus.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));

    return GlassCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('By Reading Status', style: AppTypography.h4),
          const SizedBox(height: AppSpacing.md),
          for (final entry in entries)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      readingStatusLabel(entry.key),
                      style: AppTypography.body,
                    ),
                  ),
                  Text(
                    '${entry.value}',
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
