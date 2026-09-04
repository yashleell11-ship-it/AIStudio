import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
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
          padding: EdgeInsets.all(context.space.xl2),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 420),
                child: Column(
                  children: [
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: context.radii.lg),
                    SizedBox(height: context.space.md),
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: context.radii.lg),
                    SizedBox(height: context.space.md),
                    SkeletonBox(width: double.infinity, height: 360, borderRadius: context.radii.lg),
                  ],
                ),
              ),
              SizedBox(height: context.space.xl2),
              Text(
                'Loading chapter…',
                style: context.text.body.copyWith(color: ReaderColors.muted),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
