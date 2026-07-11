/// Builds the absolute cover image URL for a library series.
String seriesCoverUrl(String apiBaseUrl, int seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}library/covers/$seriesId';
}

/// Shared Hero tag for a library series' cover, so the library grid/list and
/// the series detail screen animate as one continuous shared element rather
/// than a hard cut. Both ends must use this exact same helper.
String seriesCoverHeroTag(int seriesId) => 'series-cover-$seriesId';

/// Resolves a collection cover URL when the backend stores an absolute URL.
String? collectionCoverUrl(String? coverPath) {
  if (coverPath == null || coverPath.isEmpty) return null;
  if (coverPath.startsWith('http://') || coverPath.startsWith('https://')) {
    return coverPath;
  }
  return null;
}
