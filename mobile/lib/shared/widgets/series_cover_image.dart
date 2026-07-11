import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';

/// Cover image for a library series or source series.
///
/// Uses CachedNetworkImage with a shimmer placeholder and graceful fallback.
class SeriesCoverImage extends StatelessWidget {
  const SeriesCoverImage({
    super.key,
    required this.url,
    this.width,
    this.height,
    this.borderRadius = AppRadius.md,
    this.fit = BoxFit.cover,
  });

  final String url;
  final double? width;
  final double? height;
  final double borderRadius;
  final BoxFit fit;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius),
      child: CachedNetworkImage(
        imageUrl: url,
        width: width,
        height: height,
        fit: fit,
        fadeInDuration: const Duration(milliseconds: 250),
        placeholder: (_, __) => _Placeholder(width: width, height: height),
        errorWidget: (_, __, ___) => _ErrorPlaceholder(width: width, height: height),
      ),
    );
  }
}

class _Placeholder extends StatelessWidget {
  const _Placeholder({this.width, this.height});

  final double? width;
  final double? height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.surface2, AppColors.panel],
        ),
      ),
    );
  }
}

class _ErrorPlaceholder extends StatelessWidget {
  const _ErrorPlaceholder({this.width, this.height});

  final double? width;
  final double? height;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: width,
      height: height,
      color: AppColors.surface2,
      child: const Center(
        child: Icon(Icons.broken_image_outlined, color: AppColors.muted),
      ),
    );
  }
}
