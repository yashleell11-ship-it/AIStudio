import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_radius.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

class ReaderPageImage extends StatefulWidget {
  const ReaderPageImage({
    super.key,
    required this.imageUrl,
    required this.alt,
    required this.aspectRatio,
    this.priority = false,
    this.onLoad,
  });

  final String imageUrl;
  final String alt;
  final double aspectRatio;
  final bool priority;
  final VoidCallback? onLoad;

  @override
  State<ReaderPageImage> createState() => _ReaderPageImageState();
}

class _ReaderPageImageState extends State<ReaderPageImage> {
  int _retryToken = 0;

  void _retry() => setState(() => _retryToken++);

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: widget.aspectRatio,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Colors.black,
          borderRadius: BorderRadius.circular(AppRadius.sm),
          boxShadow: const [
            BoxShadow(
              color: Color(0x66000000),
              blurRadius: 16,
              offset: Offset(0, 8),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          child: CachedNetworkImage(
            key: ValueKey('${widget.imageUrl}:$_retryToken'),
            imageUrl: widget.imageUrl,
            fit: BoxFit.contain,
            fadeInDuration: const Duration(milliseconds: 150),
            placeholder: (_, __) => const ColoredBox(
              color: Colors.black,
              child: Center(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
            errorWidget: (_, __, ___) => ColoredBox(
              color: AppColors.void_,
              child: Center(
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.broken_image_outlined, color: AppColors.muted),
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        'Failed to load page',
                        style: AppTypography.bodySm.copyWith(color: AppColors.muted),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: AppSpacing.md),
                      OutlinedButton(onPressed: _retry, child: const Text('Retry')),
                    ],
                  ),
                ),
              ),
            ),
            imageBuilder: (context, imageProvider) {
              WidgetsBinding.instance.addPostFrameCallback((_) => widget.onLoad?.call());
              return Image(
                image: imageProvider,
                fit: BoxFit.contain,
                semanticLabel: widget.alt,
              );
            },
          ),
        ),
      ),
    );
  }
}
