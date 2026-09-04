import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Loading placeholder for the series page.
///
/// Mirrors the real layout (`SeriesDetailBody`): full-width 2:3 cover, then the
/// title/credit/summary lines, then the chapter list. A skeleton whose blocks
/// sit somewhere else than the content that replaces them reads as the page
/// jumping, which is exactly what it exists to avoid.
class SeriesDetailSkeleton extends StatelessWidget {
  const SeriesDetailSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: EdgeInsets.all(context.space.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const AspectRatio(
            aspectRatio: 2 / 3,
            child: SkeletonBox(
              width: double.infinity,
              height: double.infinity,
              borderRadius: 12,
            ),
          ),
          SizedBox(height: context.space.xl2),
          const SkeletonBox(width: 220, height: 32),
          SizedBox(height: context.space.md),
          const SkeletonBox(width: 140, height: 16),
          SizedBox(height: context.space.sm),
          const SkeletonBox(width: 200, height: 14),
          SizedBox(height: context.space.lg),
          const SkeletonBox(width: double.infinity, height: 72),
          SizedBox(height: context.space.xl2),
          const SkeletonBox(width: double.infinity, height: 48, borderRadius: 999),
          SizedBox(height: context.space.xl3),
          const SkeletonBox(width: 120, height: 20),
          SizedBox(height: context.space.lg),
          const ChapterListSkeleton(),
        ],
      ),
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
        (_) => Padding(
          padding: EdgeInsets.only(bottom: context.space.sm),
          child: const SkeletonBox(width: double.infinity, height: 64),
        ),
      ),
    );
  }
}
