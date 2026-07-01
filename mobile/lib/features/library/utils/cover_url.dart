/// Builds the absolute cover image URL for a library series.
String seriesCoverUrl(String apiBaseUrl, int seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}library/covers/$seriesId';
}

/// Resolves a collection cover URL when the backend stores an absolute URL.
String? collectionCoverUrl(String? coverPath) {
  if (coverPath == null || coverPath.isEmpty) return null;
  if (coverPath.startsWith('http://') || coverPath.startsWith('https://')) {
    return coverPath;
  }
  return null;
}
