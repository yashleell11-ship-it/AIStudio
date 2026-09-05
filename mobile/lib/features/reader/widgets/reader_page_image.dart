import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/reader/theme/reader_colors.dart';
import 'package:manhwamaniacs/features/reader/utils/page_layout.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_decode_diagnostics.dart';
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
    this.onIntrinsicSize,
    this.httpHeaders,
    this.localFile,
    this.declaredWidth,
    this.declaredHeight,
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

  /// The size the source said this page is, when it said anything at all.
  ///
  /// Not used to lay the page out — [aspectRatio] already carries that — only
  /// to tell the debug decode diagnostic what the bitmap *should* have come
  /// back as, so a decode that disagrees can be named.
  final int? declaredWidth;
  final int? declaredHeight;

  @override
  ConsumerState<ReaderPageImage> createState() => _ReaderPageImageState();
}

class _ReaderPageImageState extends ConsumerState<ReaderPageImage> {
  int _retryToken = 0;
  ImageStream? _sizeStream;
  ImageStreamListener? _sizeListener;
  bool _sizeReported = false;
  String? _checkedLocalPath;
  bool _localFileExists = false;

  void _retry() => setState(() {
        _retryToken++;
        _checkedLocalPath = null;
      });

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
  ///
  /// In a debug build this also runs for a page whose size is already known,
  /// which is the only way the decode diagnostic can compare a declared size
  /// against what the GPU actually gave back. Release builds keep exactly the
  /// old behaviour: [readerDecodeDiagnosticsEnabled] is a compile-time false.
  void _listenForIntrinsicSize() {
    if (widget.onIntrinsicSize == null && !readerDecodeDiagnosticsEnabled) {
      return;
    }
    if (_sizeReported) return;
    if (_sizeStream != null) return;
    final localFile = widget.localFile;
    if (localFile == null && widget.imageUrl.isEmpty) return;

    final headers = widget.httpHeaders ??
        apiImageHttpHeaders(
          ref.read(authTokenStoreProvider).token,
          profileId: ref.read(activeProfileProvider)?.id,
        );
    final decodeWidth = readerDecodeWidth(
      widget.viewportWidth,
      MediaQuery.devicePixelRatioOf(context),
    );
    final provider = ResizeImage.resizeIfNeeded(
      decodeWidth,
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
        reportReaderDecode(
          label: widget.alt,
          declaredWidth: widget.declaredWidth,
          declaredHeight: widget.declaredHeight,
          requestedWidth: decodeWidth,
          decodedWidth: width,
          decodedHeight: height,
        );
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

  /// Deliberately static.
  ///
  /// A spinner here is an indeterminate [AnimationController], and the reader
  /// keeps ~20 unloaded pages alive at once inside the list's 6000 px cache
  /// window — none of them wrapped in a disabled [TickerMode], because sliver
  /// children in the cache region are not. Twenty tickers marking themselves
  /// dirty every frame means the engine never reaches an idle frame: the app
  /// renders continuously while nothing is moving, which is what "feels like
  /// 30 Hz" is made of. A backdrop-coloured box is also what reads best
  /// between two pages of artwork.
  Widget _loadingBox() => _placeholderBox(
        child: ColoredBox(color: widget.backgroundColor),
      );

  /// Shared by both the network and on-device sources — the reader must not
  /// look different depending on which one served a page, only whether it
  /// loaded.
  Widget _brokenPageBox() => _placeholderBox(
        child: ColoredBox(
          color: widget.backgroundColor,
          child: Center(
            child: Padding(
              padding: EdgeInsets.all(context.space.lg),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.broken_image_outlined, color: ReaderColors.muted),
                  SizedBox(height: context.space.sm),
                  Text(
                    'Failed to load page',
                    style: context.text.bodySm.copyWith(color: ReaderColors.muted),
                    textAlign: TextAlign.center,
                  ),
                  SizedBox(height: context.space.md),
                  OutlinedButton(onPressed: _retry, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        ),
      );

  BoxFit get _boxFit => readerFitModeToBoxFit(widget.fitMode);

  /// Renders [provider], which must already carry the decode size — see
  /// [_buildLocalImage] and [_buildNetworkImage] for why the wrapping happens
  /// at the call site rather than here.
  Widget _loadedImage(ImageProvider provider) {
    return ReaderLoadedPageImage(
      image: provider,
      fitMode: widget.fitMode,
      layoutAxis: widget.layoutAxis,
      viewportWidth: widget.viewportWidth,
      viewportHeight: widget.viewportHeight,
      semanticLabel: widget.alt,
    );
  }

  /// Whether the on-device blob is still there.
  ///
  /// Checked once per path rather than on every build: this runs on the UI
  /// isolate, [build] runs whenever the reader commits a measured page, and
  /// on Android a stat under app documents storage is not reliably fast. A
  /// blob that disappears mid-session is caught by the [Image.errorBuilder]
  /// below, which is the same broken-page state this check produces.
  bool _localFileIsPresent(File file) {
    if (_checkedLocalPath != file.path) {
      _checkedLocalPath = file.path;
      _localFileExists = file.existsSync();
    }
    return _localFileExists;
  }

  /// On-device store resolution — no network, no cache manager, works with
  /// the server unreachable. A blob a user deleted by hand through the Files
  /// app (spec §3b) shows the same broken-page/retry state a network failure
  /// would, rather than a raw filesystem exception.
  ///
  /// The outer [Image] is here only to observe the load: its `child` is
  /// discarded, so it is never inflated. It must therefore be handed the
  /// **same** provider the page actually renders — a bare `FileImage` would be
  /// a different [ResizeImage] key and the page would be decoded twice, once
  /// at the blob's full native size, which for a webtoon strip is the
  /// expensive one.
  Widget _buildLocalImage(int? decodeWidth, File file) {
    if (!_localFileIsPresent(file)) return _brokenPageBox();
    final provider =
        ResizeImage.resizeIfNeeded(decodeWidth, null, FileImage(file));
    return Image(
      key: ValueKey('local:${file.path}:$_retryToken'),
      image: provider,
      frameBuilder: (context, child, frame, wasSynchronouslyLoaded) =>
          frame == null ? _loadingBox() : _loadedImage(provider),
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
      // No cross-fade: octo_image implements it by stacking the arriving page
      // over the placeholder behind two FadeTransitions, i.e. a saveLayer over
      // a full-viewport-width page, and during a fast scroll several of those
      // overlap. There is nothing to fade against either — the page already
      // occupies its reserved extent over a backdrop-coloured box before it
      // loads.
      //
      // Both halves have to be zero. Zeroing only the fade-in leaves the
      // placeholder fading out over octo_image's default second, and it is the
      // fade-*out* that holds the stack together: at zero it drops the
      // placeholder outright and the page is left painting alone.
      fadeInDuration: Duration.zero,
      fadeOutDuration: Duration.zero,
      placeholder: (_, __) => _loadingBox(),
      errorWidget: (_, __, ___) => _brokenPageBox(),
      // The raw provider CachedNetworkImage hands back, wrapped in the same
      // ResizeImage key its own memCacheWidth produced — equal keys, one
      // decode, one cache entry.
      imageBuilder: (context, imageProvider) => _loadedImage(
        ResizeImage.resizeIfNeeded(decodeWidth, null, imageProvider),
      ),
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
        seamless ? BorderRadius.zero : BorderRadius.circular(context.radii.sm);

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
