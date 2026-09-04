import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/providers/intelligence_providers.dart';
import 'package:manhwamaniacs/features/library/providers/library_list_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Recommendations — source-native (`GET /library/recommendations`). Without
/// an external catalog there is nothing to recommend beyond the followed
/// set's own genres, so the backend returns the top genres over what is
/// already followed and this screen drives a genre-filtered search from them.
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
        loading: () => ListView(
          padding: EdgeInsets.all(context.space.xl2),
          children: [
            const SkeletonBox(width: double.infinity, height: 44),
            SizedBox(height: context.space.md),
            const SkeletonBox(width: double.infinity, height: 44),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load recommendations.',
                style: context.text.body.copyWith(color: context.colors.danger),
              ),
              SizedBox(height: context.space.lg),
              FilledButton(
                onPressed: () => ref.invalidate(recommendationsProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (genres) {
          if (genres.isEmpty) {
            return EmptyState(
              icon: Icons.auto_awesome_outlined,
              message: 'No recommendations yet',
              subtitle: 'Follow a few series to see the genres you read most.',
              action: PrimaryPillButton(
                label: 'Browse Library',
                onPressed: () => context.go(Routes.libraryBrowse),
              ),
            );
          }

          return RefreshIndicator(
            color: context.colors.primary,
            onRefresh: () async => ref.invalidate(recommendationsProvider),
            child: ListView(
              padding: EdgeInsets.all(context.space.xl2),
              children: [
                const HeroHeading(text: 'Recommendations'),
                SizedBox(height: context.space.xs),
                Text(
                  'The genres you follow most — tap one to search for more.',
                  style: context.text.body.copyWith(color: context.colors.muted),
                ),
                SizedBox(height: context.space.xl2),
                Wrap(
                  spacing: context.space.sm,
                  runSpacing: context.space.sm,
                  children: [
                    for (final genre in genres)
                      _GenreChip(
                        genre: genre.genre,
                        weight: genre.weight,
                        onTap: () {
                          ref.read(searchQueryProvider.notifier).state = genre.genre;
                          context.go(Routes.search);
                        },
                      ),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _GenreChip extends StatelessWidget {
  const _GenreChip({required this.genre, required this.weight, required this.onTap});

  final String genre;
  final int weight;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: context.colors.panel,
      borderRadius: BorderRadius.circular(context.radii.full),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(context.radii.full),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: context.space.lg,
            vertical: context.space.sm,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(genre, style: context.text.labelLg),
              SizedBox(width: context.space.xs),
              Text(
                '$weight',
                style: context.text.caption.copyWith(color: context.colors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
