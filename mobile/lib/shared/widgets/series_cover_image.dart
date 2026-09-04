import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/network/api_image.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Cover image for a library series or source series.
///
/// Uses CachedNetworkImage with a shimmer placeholder and graceful fallback.
/// Attaches the session bearer token so proxied `/library/covers/*` and
/// `/sources/*/cover` routes succeed (they require authentication).
///
/// This is also the one place that asks the cover proxy for a right-sized
/// image. Every cover in the app is painted through here, so the slot width →
/// `?w=` translation lives here rather than in each of the sixteen call sites.
class SeriesCoverImage extends ConsumerWidget {
  const SeriesCoverImage({
    super.key,
    required this.url,
    this.width,
    this.height,
    this.displayWidth,
    this.borderRadius,
    this.fit = BoxFit.cover,
  });

  final String url;
  final double? width;
  final double? height;

  /// Logical width of the slot this cover is painted into, for callers whose
  /// cover stretches to fill its parent and so pass no [width] — a grid tile,
  /// the detail hero. Defaults to [width], which already *is* the slot width
  /// wherever a caller states one.
  ///
  /// Declared by the caller, never measured. The width ends up in the request
  /// URL and [CachedNetworkImage] keys its disk cache on that URL, so a width
  /// that moves buys a fresh download every time it does. A `LayoutBuilder`
  /// here would be exactly that: covers sit inside [Hero]s that resize on
  /// every frame of a flight, which would write one cache entry per frame. A
  /// declared width is constant for a device and orientation — one entry.
  final double? displayWidth;

  /// Null takes the preset's `md` corner — a default that has to be read
  /// from the tree, not baked into the constructor signature.
  final double? borderRadius;
  final BoxFit fit;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final headers = apiImageHttpHeaders(
      ref.watch(authTokenStoreProvider).token,
      profileId: ref.watch(activeProfileProvider)?.id,
    );
    final imageUrl = coverUrlAtWidth(
      url,
      coverRequestWidth(
        displayWidth ?? width,
        MediaQuery.devicePixelRatioOf(context),
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(borderRadius ?? context.radii.md),
      child: CachedNetworkImage(
        imageUrl: imageUrl,
        httpHeaders: headers,
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
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [context.colors.surface2, context.colors.panel],
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
      color: context.colors.surface2,
      child: Center(
        child: Icon(Icons.broken_image_outlined, color: context.colors.muted),
      ),
    );
  }
}
