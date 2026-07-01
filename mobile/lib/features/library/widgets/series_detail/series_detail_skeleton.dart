import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
import 'package:flutter/material.dart';

class SeriesDetailSkeleton extends StatelessWidget {
  const SeriesDetailSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      slivers: [
        const SliverToBoxAdapter(
          child: SkeletonBox(width: double.infinity, height: 280),
        ),
        SliverPadding(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          sliver: SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SkeletonBox(width: 140, height: 210, borderRadius: 16),
                    SizedBox(width: AppSpacing.xl2),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SkeletonBox(width: double.infinity, height: 32),
                          SizedBox(height: AppSpacing.md),
                          SkeletonBox(width: 180, height: 16),
                          SizedBox(height: AppSpacing.lg),
                          SkeletonBox(width: double.infinity, height: 96),
                        ],
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpacing.xl3),
                SkeletonBox(width: 160, height: 16),
                SizedBox(height: AppSpacing.lg),
                SkeletonBox(width: double.infinity, height: 200),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class ChapterListSkeleton extends StatelessWidget {
  const ChapterListSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: List.generate(
        6,
        (_) => const Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: SkeletonBox(width: double.infinity, height: 64),
        ),
      ),
    );
  }
}
