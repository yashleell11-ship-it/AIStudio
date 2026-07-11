import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';

/// A shimmering placeholder block used across every loading state.
///
/// A soft highlight sweeps across a muted base so loading screens feel alive
/// instead of frozen — kept deliberately low-contrast for AMOLED comfort. The
/// public constructor is unchanged, so every existing skeleton in the app
/// picks up the animation for free.
class SkeletonBox extends StatelessWidget {
  const SkeletonBox({
    super.key,
    required this.width,
    required this.height,
    this.borderRadius = AppRadius.md,
  });

  final double? width;
  final double height;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: SizedBox(
        width: width,
        height: height,
        child: const ShimmerFill(),
      ),
    );
  }
}

/// Fills its (bounded) constraints with the animated shimmer sweep. Use inside
/// any sized box — an image placeholder, a card slot — where passing an
/// explicit width/height isn't convenient.
class ShimmerFill extends StatefulWidget {
  const ShimmerFill({super.key});

  @override
  State<ShimmerFill> createState() => _ShimmerFillState();
}

class _ShimmerFillState extends State<ShimmerFill>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1150),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          return DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: const [
                  AppColors.surface2,
                  AppColors.glassEdge,
                  AppColors.surface2,
                ],
                stops: const [0.35, 0.5, 0.65],
                transform: _ShimmerSlide(_controller.value),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// Slides the shimmer gradient a full box-width across as [t] goes 0 → 1,
/// producing the travelling highlight band.
class _ShimmerSlide extends GradientTransform {
  const _ShimmerSlide(this.t);

  final double t;

  @override
  Matrix4 transform(Rect bounds, {TextDirection? textDirection}) {
    final dx = (2.0 * t - 1.0) * bounds.width;
    return Matrix4.translationValues(dx, 0, 0);
  }
}
