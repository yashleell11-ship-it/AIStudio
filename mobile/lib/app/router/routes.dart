/// Named route constants — single source of truth for all deep links.
abstract final class Routes {
  // ── Dashboard ──────────────────────────────────────────────────────────────
  static const String home = '/';

  // ── Library ───────────────────────────────────────────────────────────────
  static const String library = '/library';
  static const String seriesDetail = '/library/:seriesId';
  static const String reader = '/library/:seriesId/chapters/:chapterId/read';

  // ── Collections ───────────────────────────────────────────────────────────
  static const String collections = '/collections';
  static const String collectionDetail = '/collections/:collectionId';

  // ── Sources ───────────────────────────────────────────────────────────────
  static const String sources = '/sources';
  static const String sourceBrowse = '/sources/:sourceId';
  static const String sourceSeriesDetail = '/sources/:sourceId/series/:seriesId';
  static const String sourceReader =
      '/sources/:sourceId/series/:seriesId/chapters/:chapterId/read';

  // ── Downloads ─────────────────────────────────────────────────────────────
  static const String downloads = '/downloads';

  // ── Updates ───────────────────────────────────────────────────────────────
  static const String updates = '/updates';

  // ── Search ────────────────────────────────────────────────────────────────
  static const String search = '/search';

  // ── Settings ──────────────────────────────────────────────────────────────
  static const String settings = '/settings';
}

/// Helper for building concrete paths with parameters filled in.
abstract final class RoutePaths {
  static String seriesDetail(int seriesId) => '/library/$seriesId';

  static String reader(int seriesId, int chapterId) =>
      '/library/$seriesId/chapters/$chapterId/read';

  static String collectionDetail(int collectionId) => '/collections/$collectionId';

  static String sourceBrowse(String sourceId) => '/sources/$sourceId';

  static String sourceSeriesDetail(String sourceId, String seriesId) =>
      '/sources/$sourceId/series/$seriesId';

  static String sourceReader(String sourceId, String seriesId, String chapterId) =>
      '/sources/$sourceId/series/$seriesId/chapters/${Uri.encodeComponent(chapterId)}/read';
}
