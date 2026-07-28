import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
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
    return const SingleChildScrollView(
      padding: EdgeInsets.all(AppSpacing.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AspectRatio(
            aspectRatio: 2 / 3,
            child: SkeletonBox(
              width: double.infinity,
              height: double.infinity,
              borderRadius: 12,
            ),
          ),
          SizedBox(height: AppSpacing.xl2),
          SkeletonBox(width: 220, height: 32),
          SizedBox(height: AppSpacing.md),
          SkeletonBox(width: 140, height: 16),
          SizedBox(height: AppSpacing.sm),
          SkeletonBox(width: 200, height: 14),
          SizedBox(height: AppSpacing.lg),
          SkeletonBox(width: double.infinity, height: 72),
          SizedBox(height: AppSpacing.xl2),
          SkeletonBox(width: double.infinity, height: 48, borderRadius: 999),
          SizedBox(height: AppSpacing.xl3),
          SkeletonBox(width: 120, height: 20),
          SizedBox(height: AppSpacing.lg),
          ChapterListSkeleton(),
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
        (_) => const Padding(
          padding: EdgeInsets.only(bottom: AppSpacing.sm),
          child: SkeletonBox(width: double.infinity, height: 64),
        ),
      ),
    );
  }
}
