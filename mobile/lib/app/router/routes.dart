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
  /// `:seriesId` here is the follow row's `followed_id` — a handle for
  /// `PATCH`/`DELETE /library/...`, never domain identity (see
  /// `FollowedSeries` in `features/library/models/followed_series.dart`).
  static const String seriesDetail = '/library/:seriesId';

  /// The manifest-driven reader, keyed by the opaque
  /// `(sourceId, seriesKey, chapterKey)` triple — not the follow row id, so
  /// every entry point (continue reading, bookmarks, history, series detail)
  /// can link to it directly with no extra lookup.
  static const String reader =
      '/library/read/:sourceId/:seriesKey/:chapterKey';

  // ── Collections ───────────────────────────────────────────────────────────
  static const String collections = '/collections';
  static const String collectionDetail = '/collections/:collectionId';

  // ── Sources ───────────────────────────────────────────────────────────────
  static const String sources = '/sources';
  static const String sourceBrowse = '/sources/:sourceId';
  static const String sourceSeriesDetail = '/sources/:sourceId/series/:seriesId';
  static const String sourceReader =
      '/sources/:sourceId/series/:seriesId/chapters/:chapterId/read';

  // ── Updates ───────────────────────────────────────────────────────────────
  static const String updates = '/updates';

  // ── Search ────────────────────────────────────────────────────────────────
  static const String search = '/search';

  // ── More ──────────────────────────────────────────────────────────────────
  static const String more = '/more';

  // ── Downloads ─────────────────────────────────────────────────────────────
  /// A bottom-nav tab root, not a pushed detail screen: an offline library
  /// nobody can find is an offline library nobody uses, and this one was
  /// reachable only from More.
  static const String downloads = '/downloads';

  // ── OCR ───────────────────────────────────────────────────────────────────
  /// Dialogue search over extracted chapter text. Deliberately not nested
  /// under [search]: that route is the federated series search and lives in a
  /// tab shell branch, while this is a pushed full-screen route reached from
  /// More.
  static const String ocrSearch = '/ocr/search';

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
      path == Routes.search ||
      path == Routes.downloads ||
      path == Routes.more;
}

/// Helper for building concrete paths with parameters filled in.
abstract final class RoutePaths {
  static String seriesDetail(int seriesId) => '/library/$seriesId';

  /// [seriesKey] and [chapterKey] are opaque connector keys that may contain
  /// `/` (every madara-family chapter key looks like `series-slug/chapter-n`).
  /// go_router's `:seriesKey` / `:chapterKey` params each match a SINGLE path
  /// segment (`[^/]+`), so the whole key must be encoded as one segment —
  /// `Uri.encodeComponent` turns the `/` into `%2F`, which go_router
  /// percent-decodes exactly once on the way in. Per-sub-segment encoding
  /// (the backend `:path`-converter form) keeps raw slashes and makes the
  /// location grow extra segments, which never matches this route.
  static String reader(String sourceId, String seriesKey, String chapterKey) =>
      '/library/read/$sourceId/${Uri.encodeComponent(seriesKey)}'
      '/${Uri.encodeComponent(chapterKey)}';

  static String collectionDetail(int collectionId) => '/collections/$collectionId';

  static String sourceBrowse(String sourceId) => '/sources/$sourceId';

  // Source ids are flat slugs, but series/chapter ids come from the connectors
  // and can contain `/` or `%` (e.g. toonily's `series/chapter-1`). go_router
  // percent-DECODES path parameters on the way in, so encoding here is the
  // matching half of that round-trip: without it a slash-bearing id becomes an
  // extra path segment (404) and a literal `%` throws in `decodeComponent`.
  static String sourceSeriesDetail(String sourceId, String seriesId) =>
      '/sources/$sourceId/series/${Uri.encodeComponent(seriesId)}';

  static String sourceReader(String sourceId, String seriesId, String chapterId) =>
      '/sources/$sourceId/series/${Uri.encodeComponent(seriesId)}'
      '/chapters/${Uri.encodeComponent(chapterId)}/read';
}
