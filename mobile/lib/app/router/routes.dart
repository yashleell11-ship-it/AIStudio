/// Named route constants — single source of truth for all deep links.
abstract final class Routes {
  // ── Authentication ─────────────────────────────────────────────────────────
  static const String splash = '/splash';
  static const String login = '/login';
  static const String register = '/register';

  // ── Dashboard ──────────────────────────────────────────────────────────────
  static const String home = '/';

  // ── Library ───────────────────────────────────────────────────────────────
  static const String library = '/library';
  static const String libraryBrowse = '/library/browse';
  static const String recommendations = '/library/recommendations';
  static const String statistics = '/library/statistics';
  static const String readingHistory = '/library/history';
  static const String bookmarks = '/library/bookmarks';
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

  // ── More ──────────────────────────────────────────────────────────────────
  static const String more = '/more';

  // ── Settings ──────────────────────────────────────────────────────────────
  static const String settings = '/settings';
  static const String diagnostics = '/settings/diagnostics';
  static const String backup = '/settings/backup';
  static const String storage = '/settings/storage';

  // ── First-run setup ───────────────────────────────────────────────────────
  static const String setup = '/setup';
}

/// True only on the five primary tab roots — not browse, series detail, etc.
bool isMainTabRoute(String path) {
  return path == Routes.library ||
      path == Routes.sources ||
      path == Routes.downloads ||
      path == Routes.search ||
      path == Routes.more;
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
