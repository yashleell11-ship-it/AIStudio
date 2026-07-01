/// Builds the absolute cover image URL for a library series.
String seriesCoverUrl(String apiBaseUrl, int seriesId) {
  final base = apiBaseUrl.endsWith('/') ? apiBaseUrl : '$apiBaseUrl/';
  return '${base}library/covers/$seriesId';
}
