import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/dashboard_data.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/providers/dashboard_providers.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/widgets/dashboard/dashboard_sections.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/section_header.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

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
          // Hero — bleeds to edges, no horizontal padding
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

          // All other sections — padded
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              AppSpacing.xl3,
              AppSpacing.xl2,
              AppSpacing.xl6,
            ),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                QuickActionsRow(
                  onSearch: () => context.go(Routes.search),
                  onDownloads: () => context.go(Routes.downloads),
                  onUpdates: () => context.push(Routes.updates),
                  onSettings: () => context.push(Routes.settings),
                ),

                const SizedBox(height: AppSpacing.xl4),

                if (data.recentlyUpdated.isNotEmpty)
                  RecentlyUpdatedCarousel(
                    series: data.recentlyUpdated,
                    onViewAll: () => context.push(Routes.libraryBrowse),
                  )
                else
                  const _SectionEmptyMessage(
                    title: 'Recently Updated',
                    message: 'No recent updates yet.',
                    icon: Icons.trending_up_rounded,
                  ),

                const SizedBox(height: AppSpacing.xl4),

                const SectionHeader(
                  icon: Icons.bar_chart_rounded,
                  title: 'Your Stats',
                ),
                StatsGrid(stats: data.stats),

                const SizedBox(height: AppSpacing.xl4),

                if (data.continueReading.isNotEmpty)
                  ContinueReadingSection(
                    items: data.continueReading,
                    onViewAll: () => context.push(Routes.libraryBrowse),
                  )
                else
                  const _SectionEmptyMessage(
                    title: 'Continue Reading',
                    message: 'Start reading to track your progress.',
                    icon: Icons.play_arrow_rounded,
                  ),

                if (data.recentlyUpdated.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.xl4),
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
    final dateFormat = DateFormat.MMMd();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          icon: Icons.schedule_rounded,
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
                    thickness: 1,
                    color: AppColors.border.withAlpha(60),
                  ),
                _RecentUpdateRow(
                  item: series[i],
                  coverUrl: seriesCoverUrl(baseUrl, series[i].id),
                  dateStr: dateFormat.format(series[i].updatedAt),
                  onTap: () =>
                      context.push(RoutePaths.seriesDetail(series[i].id)),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}

class _RecentUpdateRow extends StatelessWidget {
  const _RecentUpdateRow({
    required this.item,
    required this.coverUrl,
    required this.dateStr,
    required this.onTap,
  });

  final SeriesSummary item;
  final String coverUrl;
  final String dateStr;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg,
            vertical: AppSpacing.md,
          ),
          child: Row(
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(AppRadius.md),
                child: SeriesCoverImage(
                  url: coverUrl,
                  width: 44,
                  height: 44,
                ),
              ),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.labelLg,
                    ),
                    const SizedBox(height: AppSpacing.xxs),
                    Text(
                      item.chapterCount > 0
                          ? '${item.chapterCount} chapters'
                          : 'No chapters',
                      style: AppTypography.caption,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(dateStr, style: AppTypography.caption),
                  const SizedBox(height: AppSpacing.xs),
                  const Icon(
                    Icons.chevron_right,
                    size: 16,
                    color: AppColors.muted,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionEmptyMessage extends StatelessWidget {
  const _SectionEmptyMessage({
    required this.title,
    required this.message,
    required this.icon,
  });

  final String title;
  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(icon: icon, title: title),
        GlassCard(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl2,
            vertical: AppSpacing.xl3,
          ),
          child: Row(
            children: [
              Icon(icon, size: 20, color: AppColors.muted.withAlpha(120)),
              const SizedBox(width: AppSpacing.md),
              Flexible(
                child: Text(
                  message,
                  style: AppTypography.body.copyWith(color: AppColors.muted),
                ),
              ),
            ],
          ),
        ),
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
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.danger.withAlpha(20),
              ),
              child: const Icon(Icons.error_outline, color: AppColors.danger, size: 32),
            ),
            const SizedBox(height: AppSpacing.xl2),
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
            const SizedBox(height: AppSpacing.xl3),
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