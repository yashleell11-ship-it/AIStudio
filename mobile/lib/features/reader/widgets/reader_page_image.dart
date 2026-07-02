import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_radius.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// Renders a fully loaded page at full width with its natural height.
///
/// This must never be wrapped in an [AspectRatio]: sources without page
/// dimensions (e.g. AsuraScans webtoon strips up to 900x16000) would be
/// letterboxed into the 2/3 fallback box and become unreadable slivers.
class ReaderLoadedPageImage extends StatelessWidget {
  const ReaderLoadedPageImage({
    super.key,
    required this.image,
    this.semanticLabel,
  });

  final ImageProvider image;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    return Image(
      image: image,
      fit: BoxFit.fitWidth,
      width: double.infinity,
      semanticLabel: semanticLabel,
    );
  }
}

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

  /// Placeholder ratio used only while the page is loading or failed;
  /// the loaded image always lays out at its intrinsic size.
  final double aspectRatio;
  final bool priority;
  final VoidCallback? onLoad;

  @override
  State<ReaderPageImage> createState() => _ReaderPageImageState();
}

class _ReaderPageImageState extends State<ReaderPageImage> {
  int _retryToken = 0;

  void _retry() => setState(() => _retryToken++);

  Widget _placeholderBox({required Widget child}) {
    return AspectRatio(
      aspectRatio: widget.aspectRatio,
      child: child,
    );
  }

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
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
          fit: BoxFit.fitWidth,
          width: double.infinity,
          fadeInDuration: const Duration(milliseconds: 150),
          placeholder: (_, __) => _placeholderBox(
            child: const ColoredBox(
              color: Colors.black,
              child: Center(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
          ),
          errorWidget: (_, __, ___) => _placeholderBox(
            child: ColoredBox(
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
          ),
          imageBuilder: (context, imageProvider) {
            WidgetsBinding.instance.addPostFrameCallback((_) => widget.onLoad?.call());
            return ReaderLoadedPageImage(
              image: imageProvider,
              semanticLabel: widget.alt,
            );
          },
        ),
      ),
    );
  }
}
