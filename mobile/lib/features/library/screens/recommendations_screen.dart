import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/widgets/library/series_grid.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class RecommendationsScreen extends ConsumerWidget {
  const RecommendationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recommendationsAsync = ref.watch(recommendationsProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        title: const Text('Recommendations'),
      ),
      body: recommendationsAsync.when(
        loading: () => GridView.builder(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            crossAxisSpacing: AppSpacing.lg,
            mainAxisSpacing: AppSpacing.lg,
            childAspectRatio: 0.52,
          ),
          itemCount: 6,
          itemBuilder: (_, __) => const SkeletonBox(width: double.infinity, height: 220),
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load recommendations.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(recommendationsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (items) {
          if (items.isEmpty) {
            return EmptyState(
              icon: Icons.auto_awesome_outlined,
              message: 'No recommendations yet',
              subtitle: 'Start reading some series to get personalized recommendations.',
              action: PrimaryPillButton(
                label: 'Browse Library',
                onPressed: () => context.go(Routes.libraryBrowse),
              ),
            );
          }

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () async => ref.invalidate(recommendationsProvider),
            child: ListView(
              padding: const EdgeInsets.all(AppSpacing.xl2),
              children: [
                const HeroHeading(text: 'Recommendations'),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Based on your reading history, tags, and authors.',
                  style: AppTypography.body.copyWith(color: AppColors.muted),
                ),
                const SizedBox(height: AppSpacing.xl2),
                SeriesGrid(
                  items: items,
                  viewMode: LibraryViewMode.grid,
                  onSeriesTap: (series) => context.push(RoutePaths.seriesDetail(series.id)),
                  onToggleFavorite: (seriesId) async {
                    await ref.read(libraryRepositoryProvider).toggleFavorite(seriesId);
                    ref.invalidate(recommendationsProvider);
                  },
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}