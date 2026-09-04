import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/reader/theme/reader_colors.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class ReaderSkeleton extends StatelessWidget {
  const ReaderSkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: ReaderColors.bg,
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: const Column(
                  children: [
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: AppRadius.lg),
                    SizedBox(height: AppSpacing.md),
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: AppRadius.lg),
                    SizedBox(height: AppSpacing.md),
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: AppRadius.lg),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.xl2),
              Text(
                'Loading chapter…',
                style: AppTypography.body.copyWith(color: ReaderColors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
