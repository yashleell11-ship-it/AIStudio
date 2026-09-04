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

  // ── Novels ────────────────────────────────────────────────────────────────
  /// The novel reader, keyed by the same opaque
  /// `(sourceId, seriesKey, chapterKey)` triple as [reader].
  ///
  /// A separate route rather than a `?kind=novel` on [reader] — the same call
  /// the web made, for the same reason and one more. The two readers share no
  /// rendering at all (one is a virtualized image strip, the other a text
  /// column), and on the phone a shared route would have to *discover* the
  /// kind before it could render anything: the source listing may not be
  /// loaded on a cold deep link, so every manga chapter would wait on a
  /// `/sources` round-trip to be told it was manga. Deciding at link time
  /// costs nothing and delays nothing.
  static const String novelReader =
      '/novels/read/:sourceId/:seriesKey/:chapterKey';

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

  /// The novel reader. Same encoding as [reader] — the whole opaque key is
  /// one percent-encoded path segment, because go_router's `:param` matches a
  /// single segment and connector keys routinely contain `/`.
  static String novelReader(
    String sourceId,
    String seriesKey,
    String chapterKey,
  ) =>
      '/novels/read/$sourceId/${Uri.encodeComponent(seriesKey)}'
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

  /// The query flag that turns either reader into "Read all" (spec R2) — the
  /// whole series as one continuous scroll, starting at [chapterId].
  ///
  /// A flag rather than a route of its own, because it *is* the same reader
  /// opened at the same chapter: the only difference is that it has been
  /// handed the rest of the series' chapter order, so it knows where to
  /// continue without asking per boundary. Every deep link, resume and
  /// bookmark into the ordinary reader keeps working untouched.
  static const String readAllQueryParam = 'all';

  static String readAll(String sourceId, String seriesKey, String chapterKey) =>
      '${reader(sourceId, seriesKey, chapterKey)}?$readAllQueryParam=1';

  /// The query parameters that open a reader at an EXACT position — what a
  /// bookmark tap builds.
  ///
  /// Two names and not one, because the unit differs by medium and silently
  /// reusing `page` for both is a real bug waiting to happen: the novel
  /// reader's `page` is a progress BUCKET (1–100, see
  /// `features/novels/utils/novel_progress.dart`), while a novel bookmark's
  /// index is a PARAGRAPH — feeding paragraph 340 in as a bucket would land
  /// the reader at the end of the chapter, confidently.
  ///
  /// [anchorQueryParam] is the fraction *within* that unit, 0.0–1.0. A
  /// fraction rather than pixels so the same link opens the same place on a
  /// phone, a tablet and the web.
  static const String anchorQueryParam = 'at';
  static const String paragraphQueryParam = 'para';

  /// The manga reader at page [page], [fraction] of the way down it.
  static String readerAt(
    String sourceId,
    String seriesKey,
    String chapterKey, {
    required int page,
    required double fraction,
  }) =>
      '${reader(sourceId, seriesKey, chapterKey)}'
      '?page=$page&$anchorQueryParam=${_fraction(fraction)}';

  /// The novel reader at paragraph [paragraph] (1-based), [fraction] of the
  /// way through it.
  static String novelReaderAt(
    String sourceId,
    String seriesKey,
    String chapterKey, {
    required int paragraph,
    required double fraction,
  }) =>
      '${novelReader(sourceId, seriesKey, chapterKey)}'
      '?$paragraphQueryParam=$paragraph&$anchorQueryParam=${_fraction(fraction)}';

  /// Four decimals: the same precision the server rounds `position_fraction`
  /// to, and far finer than a pixel on any page anyone reads.
  static String _fraction(double value) =>
      value.clamp(0.0, 1.0).toStringAsFixed(4);

  static String sourceReadAll(
    String sourceId,
    String seriesId,
    String chapterId,
  ) =>
      '${sourceReader(sourceId, seriesId, chapterId)}?$readAllQueryParam=1';
}

/// Whether a reader route's query asks for Read-all. Tolerant of the shapes a
/// hand-typed or round-tripped link takes (`all=1`, `all=true`, bare `all`) —
/// the flag is a request, not a protocol.
/// The `at=` fraction on a reader link, or null when there is none.
///
/// Null and not 0.0 for an absent or unparseable value: "no anchor" and "the
/// very top of the unit" are different requests, and only the first may fall
/// back to the persisted scroll position.
double? readerAnchorFraction(Map<String, String> queryParameters) {
  final raw = queryParameters[RoutePaths.anchorQueryParam];
  if (raw == null || raw.isEmpty) return null;
  final value = double.tryParse(raw);
  if (value == null || value.isNaN) return null;
  return value.clamp(0.0, 1.0);
}

/// The 1-based `para=` index on a novel reader link, or null.
int? readerAnchorParagraph(Map<String, String> queryParameters) {
  final raw = queryParameters[RoutePaths.paragraphQueryParam];
  if (raw == null || raw.isEmpty) return null;
  final value = int.tryParse(raw);
  return value == null || value < 1 ? null : value;
}

bool isReadAllRequest(Map<String, String> queryParameters) {
  if (!queryParameters.containsKey(RoutePaths.readAllQueryParam)) return false;
  final value = queryParameters[RoutePaths.readAllQueryParam]?.toLowerCase();
  return value == null || value.isEmpty || value == '1' || value == 'true';
}
