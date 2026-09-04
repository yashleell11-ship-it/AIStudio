import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/reader/theme/reader_colors.dart';
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
    this.backgroundColor = ReaderColors.bg,
    this.layoutAxis = Axis.vertical,
    this.viewportWidth,
    this.viewportHeight,
    this.priority = false,
    this.onLoad,
    this.onIntrinsicSize,
    this.httpHeaders,
    this.localFile,
  });

  final String imageUrl;
  final String alt;

  /// On-device chapter store resolution (1c-M3): when non-null, this page
  /// renders from disk and [imageUrl] is never fetched at all — no network,
  /// no cache manager, works with the server unreachable. The caller (the
  /// reader screens, not this widget) decides which it got; this widget just
  /// prefers whichever it was handed.
  final File? localFile;

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

  /// Reports the page's real pixel dimensions the moment the decoder knows
  /// them.
  ///
  /// Most sources never send page dimensions, so the list has to reserve space
  /// for a page it has not seen. Decoding is the first and only chance to learn
  /// the truth — and it happens before the image is painted, so a caller that
  /// reserves extents from this never shows a mis-sized page at all. Fires at
  /// most once. Pass ``null`` when the size is already known: it saves resolving
  /// the image a second time.
  final void Function(int pixelWidth, int pixelHeight)? onIntrinsicSize;

  /// Optional auth headers for proxied `/sources/*/pages/*/image` URLs.
  final Map<String, String>? httpHeaders;

  @override
  ConsumerState<ReaderPageImage> createState() => _ReaderPageImageState();
}

class _ReaderPageImageState extends ConsumerState<ReaderPageImage> {
  int _retryToken = 0;
  ImageStream? _sizeStream;
  ImageStreamListener? _sizeListener;
  bool _sizeReported = false;

  void _retry() => setState(() => _retryToken++);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _listenForIntrinsicSize();
  }

  @override
  void dispose() {
    _detachSizeListener();
    super.dispose();
  }

  /// Resolve the page once purely to learn its dimensions.
  ///
  /// Deliberately the same [ResizeImage] key the rendered page and the
  /// prefetcher use, so this is a cache hit and never a second decode. The
  /// downsampled bitmap keeps the source's aspect ratio, which is all the
  /// caller wants. Prefers the on-device file over the network for exactly
  /// the same reason the rendered page does — an offline chapter must never
  /// need a network round trip just to learn a page's aspect ratio.
  void _listenForIntrinsicSize() {
    if (widget.onIntrinsicSize == null || _sizeReported) return;
    if (_sizeStream != null) return;
    final localFile = widget.localFile;
    if (localFile == null && widget.imageUrl.isEmpty) return;

    final headers = widget.httpHeaders ??
        apiImageHttpHeaders(
          ref.read(authTokenStoreProvider).token,
          profileId: ref.read(activeProfileProvider)?.id,
        );
    final provider = ResizeImage.resizeIfNeeded(
      readerDecodeWidth(
        widget.viewportWidth,
        MediaQuery.devicePixelRatioOf(context),
      ),
      null,
      localFile != null
          ? FileImage(localFile) as ImageProvider
          : CachedNetworkImageProvider(widget.imageUrl, headers: headers),
    );

    final stream = provider.resolve(createLocalImageConfiguration(context));
    final listener = ImageStreamListener(
      (info, _) {
        final width = info.image.width;
        final height = info.image.height;
        // The completer clones the ImageInfo per listener, so this one is ours
        // to release — holding it would pin the full bitmap for the session.
        info.dispose();
        _sizeReported = true;
        _detachSizeListener();
        widget.onIntrinsicSize?.call(width, height);
      },
      // A page that never loads keeps its reserved fallback extent; there is
      // nothing better to say about its size.
      onError: (_, __) => _detachSizeListener(),
    );
    // Assigned before subscribing: an already-decoded page calls the listener
    // back synchronously from inside addListener, and the detach it triggers
    // has to be able to see what it is detaching from.
    _sizeStream = stream;
    _sizeListener = listener;
    stream.addListener(listener);
  }

  void _detachSizeListener() {
    final listener = _sizeListener;
    if (listener != null) _sizeStream?.removeListener(listener);
    _sizeListener = null;
    _sizeStream = null;
  }

  Widget _placeholderBox({required Widget child}) {
    return AspectRatio(
      aspectRatio: widget.aspectRatio,
      child: child,
    );
  }

  Widget _loadingBox() => _placeholderBox(
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
      );

  /// Shared by both the network and on-device sources — the reader must not
  /// look different depending on which one served a page, only whether it
  /// loaded.
  Widget _brokenPageBox() => _placeholderBox(
        child: ColoredBox(
          color: widget.backgroundColor,
          child: Center(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.broken_image_outlined, color: ReaderColors.muted),
                  const SizedBox(height: AppSpacing.sm),
                  Text(
                    'Failed to load page',
                    style: AppTypography.bodySm.copyWith(color: ReaderColors.muted),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: AppSpacing.md),
                  OutlinedButton(onPressed: _retry, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        ),
      );

  BoxFit get _boxFit => readerFitModeToBoxFit(widget.fitMode);

  Widget _loadedImage(int? decodeWidth, ImageProvider provider) {
    // Wrap with the same ResizeImage the widget's memCacheWidth uses so this
    // render reuses the already-decoded, downsampled bitmap instead of
    // decoding the page a second time at full resolution.
    return ReaderLoadedPageImage(
      image: ResizeImage.resizeIfNeeded(decodeWidth, null, provider),
      fitMode: widget.fitMode,
      layoutAxis: widget.layoutAxis,
      viewportWidth: widget.viewportWidth,
      viewportHeight: widget.viewportHeight,
      semanticLabel: widget.alt,
    );
  }

  /// On-device store resolution — no network, no cache manager, works with
  /// the server unreachable. [File.existsSync] is checked up front: a blob a
  /// user deleted by hand through the Files app (spec §3b) shows the same
  /// broken-page/retry state a network failure would, rather than a raw
  /// filesystem exception.
  Widget _buildLocalImage(int? decodeWidth, File file) {
    if (!file.existsSync()) return _brokenPageBox();
    return Image(
      key: ValueKey('local:${file.path}:$_retryToken'),
      image: FileImage(file),
      fit: _boxFit,
      frameBuilder: (context, child, frame, wasSynchronouslyLoaded) {
        if (frame == null) return _loadingBox();
        WidgetsBinding.instance.addPostFrameCallback((_) => widget.onLoad?.call());
        return _loadedImage(decodeWidth, FileImage(file));
      },
      errorBuilder: (context, error, stackTrace) => _brokenPageBox(),
    );
  }

  Widget _buildNetworkImage(int? decodeWidth, Map<String, String>? headers) {
    return CachedNetworkImage(
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
      placeholder: (_, __) => _loadingBox(),
      errorWidget: (_, __, ___) => _brokenPageBox(),
      imageBuilder: (context, imageProvider) {
        WidgetsBinding.instance.addPostFrameCallback((_) => widget.onLoad?.call());
        return _loadedImage(decodeWidth, imageProvider);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final headers = widget.httpHeaders ??
        apiImageHttpHeaders(
          ref.watch(authTokenStoreProvider).token,
          profileId: ref.watch(activeProfileProvider)?.id,
        );

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

    // On-device store first, network second (spec §3) — and the reader does
    // not know or care which it got beyond this one branch.
    final localFile = widget.localFile;
    final image = localFile != null
        ? _buildLocalImage(decodeWidth, localFile)
        : _buildNetworkImage(decodeWidth, headers);

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
