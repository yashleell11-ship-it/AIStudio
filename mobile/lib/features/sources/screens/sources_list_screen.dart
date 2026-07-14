import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/responsive.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/source_branding.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class SourcesListScreen extends ConsumerWidget {
  const SourcesListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return const Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.md,
              ),
              child: HeroHeading(text: 'Sources', fontSize: 40),
            ),
            Expanded(child: _SourcesBody()),
          ],
        ),
      ),
    );
  }
}

class _SourcesBody extends ConsumerWidget {
  const _SourcesBody();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sourcesAsync = ref.watch(sourcesListProvider);
    final pinnedIds = ref.watch(pinnedSourcesProvider);

    return sourcesAsync.when(
        loading: () => _SourcesGridSkeleton(columns: context._sourceColumns),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError
                    ? error.userMessage
                    : 'Failed to load sources.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(sourcesListProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (sources) {
          if (sources.isEmpty) {
            return const EmptyState(
              icon: Icons.public_off,
              message: 'No sources installed',
            );
          }

          final byId = {for (final s in sources) s.id: s};
          final pinned = pinnedIds
              .map((id) => byId[id])
              .whereType<SourceSummary>()
              .toList();
          final rest = sources
              .where((s) => !pinnedIds.contains(s.id))
              .toList()
            ..sort((a, b) => a.name.compareTo(b.name));

          final tiles = [...pinned, ...rest];
          final columns = context._sourceColumns;

          void onTap(SourceSummary s) =>
              context.go(RoutePaths.sourceBrowse(s.id));

          void onLongPress(SourceSummary s) {
            ref.read(pinnedSourcesProvider.notifier).toggle(s.id);
            final isPinned = pinnedIds.contains(s.id);
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(
                  isPinned ? '${s.name} unpinned' : '${s.name} pinned',
                ),
                duration: const Duration(seconds: 2),
              ),
            );
          }

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () async => ref.invalidate(sourcesListProvider),
            child: GridView.builder(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.lg,
                AppSpacing.xl7 + MediaQuery.paddingOf(context).bottom,
              ),
              physics: const AlwaysScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                mainAxisSpacing: AppSpacing.xl2,
                crossAxisSpacing: AppSpacing.md,
                childAspectRatio: 0.72,
              ),
              itemCount: tiles.length,
              itemBuilder: (context, index) {
                final source = tiles[index];
                final isPinned = pinnedIds.contains(source.id);
                return FadeIn(
                  delay: Duration(milliseconds: (index % 12) * 35),
                  offset: const Offset(0, 16),
                  child: _SourceTile(
                    source: source,
                    isPinned: isPinned,
                    onTap: () => onTap(source),
                    onLongPress: () => onLongPress(source),
                  ),
                );
              },
            ),
          );
        },
      );
  }
}

extension on BuildContext {
  int get _sourceColumns {
    final w = screenWidth;
    if (w < 360) return 3;
    if (w < 520) return 4;
    if (w < Breakpoints.tablet) return 5;
    return 6;
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({
    required this.source,
    required this.onTap,
    required this.onLongPress,
    this.isPinned = false,
  });

  final SourceSummary source;
  final VoidCallback onTap;
  final VoidCallback onLongPress;
  final bool isPinned;

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      onLongPress: onLongPress,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.xl2),
          border: Border.all(
            color: isPinned ? AppColors.primary.withAlpha(90) : AppColors.border,
          ),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.md,
          ),
          child: Column(
            children: [
              Expanded(
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    Center(
                      child: SourceLogo(
                        id: source.id,
                        name: source.name,
                        iconUrl: source.iconUrl,
                        size: 60,
                      ),
                    ),
                    if (isPinned)
                      const Positioned(
                        top: 0,
                        right: 0,
                        child: Icon(
                          Icons.push_pin,
                          size: 14,
                          color: AppColors.primary,
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                source.name,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: AppTypography.h1.copyWith(
                  fontSize: 12,
                  height: 1.15,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SourcesGridSkeleton extends StatelessWidget {
  const _SourcesGridSkeleton({required this.columns});

  final int columns;

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      padding: const EdgeInsets.all(AppSpacing.lg),
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: columns,
        mainAxisSpacing: AppSpacing.xl2,
        crossAxisSpacing: AppSpacing.md,
        childAspectRatio: 0.72,
      ),
      itemCount: columns * 4,
      itemBuilder: (_, __) => DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.xl2),
          border: Border.all(color: AppColors.border),
        ),
        child: const Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.xs,
            vertical: AppSpacing.md,
          ),
          child: Column(
            children: [
              Expanded(
                child: Center(
                  child: SkeletonBox(
                    width: 56,
                    height: 56,
                    borderRadius: AppRadius.lg,
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.sm),
              SkeletonBox(width: 48, height: 10),
            ],
          ),
        ),
      ),
    );
  }
}
