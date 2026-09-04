import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class CollectionsSkeleton extends StatelessWidget {
  const CollectionsSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: EdgeInsets.all(context.space.xl2),
      itemCount: 4,
      separatorBuilder: (_, __) => SizedBox(height: context.space.lg),
      itemBuilder: (_, __) => SkeletonBox(
        width: double.infinity,
        height: 140,
        borderRadius: context.radii.xl,
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
          padding: EdgeInsets.all(context.space.xl2),
          sliver: SliverGrid(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: context.space.lg,
              mainAxisSpacing: context.space.lg,
              childAspectRatio: 0.52,
            ),
            delegate: SliverChildBuilderDelegate(
              (_, __) => SkeletonBox(
                width: double.infinity,
                height: 220,
                borderRadius: context.radii.xl,
              ),
              childCount: 6,
            ),
          ),
        ),
      ],
    );
  }
}
