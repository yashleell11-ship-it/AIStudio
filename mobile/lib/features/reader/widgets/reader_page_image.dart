import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_image_cache.dart';
import 'package:manhwamaniacs/features/settings/models/reader_defaults.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

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

class ReaderPageImage extends ConsumerStatefulWidget {
  const ReaderPageImage({
    super.key,
    required this.imageUrl,
    required this.alt,
    required this.aspectRatio,
    required this.fitMode,
    this.backgroundColor = AppColors.bg,
    this.layoutAxis = Axis.vertical,
    this.viewportWidth,
    this.viewportHeight,
    this.priority = false,
    this.onLoad,
    this.httpHeaders,
  });

  final String imageUrl;
  final String alt;

  /// Placeholder ratio used only while the page is loading or failed;
  /// the loaded image always lays out at its intrinsic size.
  final double aspectRatio;
  final ReaderFitMode fitMode;

  /// Reader backdrop colour. Fills any letterbox bars and the placeholder so a
  /// page never shows a black seam that clashes with the chosen backdrop.
  final Color backgroundColor;
  final Axis layoutAxis;
  final double? viewportWidth;
  final double? viewportHeight;
  final bool priority;
  final VoidCallback? onLoad;

  /// Optional auth headers for proxied `/sources/*/pages/*/image` URLs.
  final Map<String, String>? httpHeaders;

  @override
  ConsumerState<ReaderPageImage> createState() => _ReaderPageImageState();
}

class _ReaderPageImageState extends ConsumerState<ReaderPageImage> {
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
    final headers = widget.httpHeaders ??
        apiImageHttpHeaders(ref.watch(authTokenStoreProvider).token);

    // Decode pages at display size, not the source's native resolution — the
    // key memory/GC win for tall webtoon strips. Kept consistent with the
    // prefetch provider so both share one ImageCache entry (single decode).
    final decodeWidth = readerDecodeWidth(
      widget.viewportWidth,
      MediaQuery.devicePixelRatioOf(context),
    );

    // Vertical (webtoon) reading is a continuous strip: pages must butt up
    // flush with no rounded corners or drop shadow, or every page join reads
    // as a dark seam. Only the paged horizontal reader keeps the card look.
    final seamless = widget.layoutAxis == Axis.vertical;
    final borderRadius =
        seamless ? BorderRadius.zero : BorderRadius.circular(AppRadius.sm);

    final image = CachedNetworkImage(
      key: ValueKey('${widget.imageUrl}:$_retryToken'),
      imageUrl: widget.imageUrl,
      httpHeaders: headers,
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
        child: ColoredBox(
          color: widget.backgroundColor,
          child: const Center(
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
          color: widget.backgroundColor,
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
    );

    // Seamless (vertical) pages need no clip or shadow — the backdrop-coloured
    // box behind the image absorbs any letterbox bars so joins stay invisible.
    if (seamless) {
      return ColoredBox(color: widget.backgroundColor, child: image);
    }

    return DecoratedBox(
      decoration: BoxDecoration(
        color: widget.backgroundColor,
        borderRadius: borderRadius,
        boxShadow: const [
          BoxShadow(
            color: Color(0x66000000),
            blurRadius: 16,
            offset: Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: borderRadius,
        child: image,
      ),
    );
  }
}
