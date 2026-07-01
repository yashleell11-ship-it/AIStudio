import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_data.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/providers/dashboard_providers.dart';
import 'package:aistudio_mobile/features/library/utils/cover_url.dart';
import 'package:aistudio_mobile/features/library/widgets/dashboard/dashboard_sections.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/section_header.dart';
import 'package:aistudio_mobile/shared/widgets/series_cover_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashboardAsync = ref.watch(dashboardProvider);

    return Scaffold(
      body: dashboardAsync.when(
        loading: () => const DashboardSkeleton(),
        error: (error, _) => _DashboardError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.invalidate(dashboardProvider),
        ),
        data: (data) => _DashboardContent(data: data),
      ),
    );
  }
}

class _DashboardContent extends ConsumerWidget {
  const _DashboardContent({required this.data});

  final DashboardData data;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (data.isEmpty) {
      return RefreshIndicator(
        onRefresh: () async => ref.invalidate(dashboardProvider),
        color: AppColors.primary,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverFillRemaining(
              hasScrollBody: false,
              child: EmptyState(
                icon: Icons.menu_book_outlined,
                message: 'Your library is empty',
                subtitle: 'Import a library to see your dashboard.',
                action: FilledButton(
                  onPressed: () => context.go(Routes.search),
                  child: const Text('Explore Search'),
                ),
              ),
            ),
          ],
        ),
      );
    }

    final firstContinue =
        data.continueReading.isNotEmpty ? data.continueReading.first : null;

    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(dashboardProvider);
        await ref.read(dashboardProvider.future);
      },
      color: AppColors.primary,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(
            child: DashboardHero(
              firstContinueItem: firstContinue,
              onBrowseLibrary: () => context.push(Routes.libraryBrowse),
              onContinueReading: firstContinue == null
                  ? () {}
                  : () => context.push(
                        '${RoutePaths.seriesDetail(firstContinue.seriesId)}/chapters/${firstContinue.chapterId}/read',
                      ),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              0,
              AppSpacing.xl2,
              AppSpacing.xl3,
            ),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                QuickActionsRow(
                  onSearch: () => context.go(Routes.search),
                  onDownloads: () => context.go(Routes.downloads),
                  onUpdates: () => context.push(Routes.updates),
                  onSettings: () => context.push(Routes.settings),
                ),
                const SizedBox(height: AppSpacing.xl3),
                if (data.recentlyUpdated.isNotEmpty)
                  RecentlyUpdatedCarousel(
                    series: data.recentlyUpdated,
                    onViewAll: () => context.push(Routes.libraryBrowse),
                  )
                else
                  const _SectionEmptyMessage(
                    title: 'Recently Updated',
                    message: 'No recent updates yet.',
                  ),
                const SizedBox(height: AppSpacing.xl3),
                StatsGrid(stats: data.stats),
                const SizedBox(height: AppSpacing.xl3),
                ContinueReadingSection(
                  items: data.continueReading,
                  onViewAll: () => context.push(Routes.libraryBrowse),
                ),
                if (data.continueReading.isEmpty)
                  const _SectionEmptyMessage(
                    title: 'Continue Reading',
                    message: 'Start reading to track your progress.',
                  ),
                if (data.recentlyUpdated.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.xl3),
                  _RecentUpdatesList(series: data.recentlyUpdated),
                ],
              ]),
            ),
          ),
        ],
      ),
    );
  }
}

class _RecentUpdatesList extends ConsumerWidget {
  const _RecentUpdatesList({required this.series});

  final List<SeriesSummary> series;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final dateFormat = DateFormat.yMMMd();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          icon: Icons.schedule,
          title: 'Recent Updates',
          onViewAll: () => context.push(Routes.libraryBrowse),
        ),
        GlassCard(
          child: Column(
            children: [
              for (var i = 0; i < series.length; i++) ...[
                if (i > 0)
                  Divider(
                    height: 1,
                    color: AppColors.border.withAlpha(77),
                  ),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.sm,
                  ),
                  child: Row(
                    children: [
                      SeriesCoverImage(
                        url: seriesCoverUrl(baseUrl, series[i].id),
                        width: 48,
                        height: 48,
                      ),
                      const SizedBox(width: AppSpacing.md),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              series[i].title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: AppTypography.labelLg,
                            ),
                            Text(
                              series[i].chapterCount > 0
                                  ? '${series[i].chapterCount} chapters'
                                  : 'No chapters',
                              style: AppTypography.caption,
                            ),
                          ],
                        ),
                      ),
                      Text(
                        dateFormat.format(series[i].updatedAt),
                        style: AppTypography.caption,
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      FilledButton(
                        onPressed: () =>
                            context.push(RoutePaths.seriesDetail(series[i].id)),
                        style: FilledButton.styleFrom(
                          minimumSize: const Size(64, 32),
                          padding: const EdgeInsets.symmetric(
                            horizontal: AppSpacing.md,
                          ),
                          textStyle: AppTypography.label,
                        ),
                        child: const Text('Read'),
                      ),
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _SectionEmptyMessage extends StatelessWidget {
  const _SectionEmptyMessage({
    required this.title,
    required this.message,
  });

  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: AppTypography.labelLg),
        const SizedBox(height: AppSpacing.sm),
        Text(message, style: AppTypography.body.copyWith(color: AppColors.muted)),
      ],
    );
  }
}

class _DashboardError extends StatelessWidget {
  const _DashboardError({
    required this.error,
    required this.onRetry,
  });

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 48),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Could not load dashboard',
              style: AppTypography.h3,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl2),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
            ),
          ],
        ),
      ),
    );
  }
}
