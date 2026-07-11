import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class CollectionsSkeleton extends StatelessWidget {
  const CollectionsSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      itemCount: 4,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.lg),
      itemBuilder: (_, __) => const SkeletonBox(
        width: double.infinity,
        height: 140,
        borderRadius: AppRadius.xl,
      ),
    );
  }
}

class CollectionDetailSkeleton extends StatelessWidget {
  const CollectionDetailSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        const SliverToBoxAdapter(
          child: SkeletonBox(width: double.infinity, height: 220),
        ),
        SliverPadding(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          sliver: SliverGrid(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: AppSpacing.lg,
              mainAxisSpacing: AppSpacing.lg,
              childAspectRatio: 0.52,
            ),
            delegate: SliverChildBuilderDelegate(
              (_, __) => const SkeletonBox(
                width: double.infinity,
                height: 220,
                borderRadius: AppRadius.xl,
              ),
              childCount: 6,
            ),
          ),
        ),
      ],
    );
  }
}
