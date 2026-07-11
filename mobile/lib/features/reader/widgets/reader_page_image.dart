import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_image_cache.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';

/// Renders a fully loaded page using the configured fit mode.
///
/// This must never be wrapped in an [AspectRatio]: sources without page
/// dimensions (e.g. AsuraScans webtoon strips up to 900x16000) would be
/// letterboxed into the 2/3 fallback box and become unreadable slivers.
class ReaderLoadedPageImage extends StatelessWidget {
  const ReaderLoadedPageImage({
    super.key,
    required this.image,
    required this.fitMode,
    this.layoutAxis = Axis.vertical,
    this.viewportWidth,
    this.viewportHeight,
    this.semanticLabel,
  });

  final ImageProvider image;
  final ReaderFitMode fitMode;
  final Axis layoutAxis;
  final double? viewportWidth;
  final double? viewportHeight;
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) {
    final boxFit = readerFitModeToBoxFit(fitMode);
    final width = viewportWidth;
    final height = viewportHeight;

    Widget loadedImage = Image(
      image: image,
      fit: boxFit,
      semanticLabel: semanticLabel,
    );

    if (layoutAxis == Axis.vertical) {
      switch (fitMode) {
        case ReaderFitMode.width:
          loadedImage = SizedBox(width: double.infinity, child: loadedImage);
        case ReaderFitMode.height:
          if (height != null) {
            loadedImage = SizedBox(height: height, child: loadedImage);
          }
        case ReaderFitMode.screen:
          if (width != null && height != null) {
            loadedImage = SizedBox(width: width, height: height, child: loadedImage);
          }
      }
    } else {
      switch (fitMode) {
        case ReaderFitMode.width:
          if (width != null) {
            loadedImage = SizedBox(width: width, child: loadedImage);
          }
        case ReaderFitMode.height:
          if (height != null) {
            loadedImage = SizedBox(height: height, child: loadedImage);
          }
        case ReaderFitMode.screen:
          if (width != null && height != null) {
            loadedImage = SizedBox(width: width, height: height, child: loadedImage);
          }
      }
    }

    return loadedImage;
  }
}

class ReaderPageImage extends StatefulWidget {
  const ReaderPageImage({
    super.key,
    required this.imageUrl,
    required this.alt,
    required this.aspectRatio,
    required this.fitMode,
    this.layoutAxis = Axis.vertical,
    this.viewportWidth,
    this.viewportHeight,
    this.priority = false,
    this.onLoad,
  });

  final String imageUrl;
  final String alt;

  /// Placeholder ratio used only while the page is loading or failed;
  /// the loaded image always lays out at its intrinsic size.
  final double aspectRatio;
  final ReaderFitMode fitMode;
  final Axis layoutAxis;
  final double? viewportWidth;
  final double? viewportHeight;
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

  BoxFit get _boxFit => readerFitModeToBoxFit(widget.fitMode);

  @override
  Widget build(BuildContext context) {
    // Decode pages at display size, not the source's native resolution — the
    // key memory/GC win for tall webtoon strips. Kept consistent with the
    // prefetch provider so both share one ImageCache entry (single decode).
    final decodeWidth = readerDecodeWidth(
      widget.viewportWidth,
      MediaQuery.devicePixelRatioOf(context),
    );

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
          fit: _boxFit,
          memCacheWidth: decodeWidth,
          width: widget.layoutAxis == Axis.vertical &&
                  widget.fitMode == ReaderFitMode.width
              ? double.infinity
              : null,
          height: widget.layoutAxis == Axis.horizontal &&
                  widget.fitMode == ReaderFitMode.height
              ? double.infinity
              : null,
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
            // Wrap with the same ResizeImage the widget's memCacheWidth uses so
            // this render reuses the already-decoded, downsampled bitmap
            // instead of decoding the page a second time at full resolution.
            return ReaderLoadedPageImage(
              image: ResizeImage.resizeIfNeeded(decodeWidth, null, imageProvider),
              fitMode: widget.fitMode,
              layoutAxis: widget.layoutAxis,
              viewportWidth: widget.viewportWidth,
              viewportHeight: widget.viewportHeight,
              semanticLabel: widget.alt,
            );
          },
        ),
      ),
    );
  }
}
