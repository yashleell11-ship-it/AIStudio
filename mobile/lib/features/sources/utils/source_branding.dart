import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';

/// Maps known source IDs to their site favicon URLs for branding. Shared by the
/// sources list and the source browser so the mapping lives in exactly one
/// place. Prefer [iconUrl] from the API when the backend supplies it.
String? sourceFaviconUrl(String sourceId) {
  const map = <String, String>{
    'mangadex': 'https://mangadex.org/favicon.ico',
    'toonily': 'https://toonily.com/favicon.ico',
    'asura': 'https://asuracomic.net/favicon.ico',
    'asurascans': 'https://asuracomic.net/favicon.ico',
    'mangakatana': 'https://mangakatana.com/favicon.ico',
    'webtoons': 'https://www.webtoons.com/favicon.ico',
    'comick': 'https://comick.io/favicon.ico',
    'bato': 'https://bato.to/favicon.ico',
    'manganelo': 'https://manganelo.com/favicon.ico',
    'manganato': 'https://manganato.com/favicon.ico',
    'reaperscans': 'https://reaperscans.com/favicon.ico',
    'flamescans': 'https://flamescans.org/favicon.ico',
    'luminousscans': 'https://luminousscans.com/favicon.ico',
  };
  return map[sourceId.toLowerCase()];
}

/// Best-effort display name for a source id when the resolved [SourceSummary]
/// name isn't available yet (e.g. the sources list is still loading).
String prettifySourceId(String sourceId) =>
    sourceId.isEmpty ? sourceId : sourceId[0].toUpperCase() + sourceId.substring(1);

/// Source logo: shows the site favicon when known, falling back to a colored
/// letter avatar for unknown connectors. Sized so it works both as a 44px list
/// avatar and a compact app-bar mark.
class SourceLogo extends StatelessWidget {
  const SourceLogo({
    super.key,
    required this.id,
    required this.name,
    this.iconUrl,
    this.size = 44,
  });

  final String id;
  final String name;
  final String? iconUrl;
  final double size;

  @override
  Widget build(BuildContext context) {
    final faviconUrl = iconUrl ?? sourceFaviconUrl(id);

    return Container(
      width: size,
      height: size,
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(context.radii.md),
        color: context.colors.surface2,
        border: Border.all(color: context.colors.glassEdge),
      ),
      child: faviconUrl != null
          ? CachedNetworkImage(
              imageUrl: faviconUrl,
              fit: BoxFit.contain,
              width: size,
              height: size,
              placeholder: (_, __) => _LetterAvatar(name: name, size: size),
              errorWidget: (_, __, ___) => _LetterAvatar(name: name, size: size),
            )
          : _LetterAvatar(name: name, size: size),
    );
  }
}

class _LetterAvatar extends StatelessWidget {
  const _LetterAvatar({required this.name, required this.size});

  final String name;
  final double size;

  @override
  Widget build(BuildContext context) {
    final initial = name.trim().isEmpty ? '?' : name.trim()[0].toUpperCase();
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [context.colors.surface2, context.colors.panel],
        ),
      ),
      child: Center(
        child: Text(
          initial,
          style: (size >= 40 ? context.text.h4 : context.text.labelLg)
              .copyWith(color: context.colors.violet400),
        ),
      ),
    );
  }
}
