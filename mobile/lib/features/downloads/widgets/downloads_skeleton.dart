import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class DownloadsSkeleton extends StatelessWidget {
  const DownloadsSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SkeletonBox(width: 180, height: 36),
          const SizedBox(height: AppSpacing.xl2),
          const SkeletonBox(width: double.infinity, height: 120, borderRadius: AppRadius.xl),
          const SizedBox(height: AppSpacing.xl2),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: List.generate(
                5,
                (_) => const Padding(
                  padding: EdgeInsets.only(right: AppSpacing.sm),
                  child: SkeletonBox(width: 110, height: 36, borderRadius: AppRadius.full),
                ),
              ),
            ),
          ),
          const SizedBox(height: AppSpacing.xl2),
          ...List.generate(
            3,
            (_) => const Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.lg),
              child: SkeletonBox(width: double.infinity, height: 120, borderRadius: AppRadius.xl),
            ),
          ),
        ],
      ),
    );
  }
}
