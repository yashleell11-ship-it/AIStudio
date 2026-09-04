/// Content mode — the app-wide Manga / Novels switch.
///
/// Novels are not a second kind of row inside the manga app: they are a
/// different reading life with a different library, and mixing a 61k-title
/// novel archive into a sources list of manhwa sites makes both harder to
/// use. So the mode scopes EVERY list that could hold either kind (library,
/// browse, sources, search, updates, downloads, collections, history,
/// bookmarks, statistics), the same way a profile scopes them.
///
/// Two invariants this file exists to hold:
///
/// 1. **Manga mode is today's app, exactly.** The manga predicate is "not a
///    novel", never "is a manga" — so a connector that omits `content_kind`,
///    or a deployment with `MM_NOVELS_ENABLED` off (where the registry hides
///    novel sources entirely and nothing is ever tagged `"novel"`), filters to
///    the identical list it renders today. The filter is a no-op, not a
///    rewrite.
///
/// 2. **Flag off means no mode at all.** With novels disabled the switch does
///    not render and the effective mode is forced to manga regardless of what
///    is stored — a profile that used Novels mode while the flag was on cannot
///    come back to a half-empty app after it is turned off again.
library;

import 'package:manhwamaniacs/features/sources/models/source.dart';

enum ContentMode {
  manga,
  novel;

  /// What the owner reads daily, and what every existing library row is.
  static const ContentMode fallback = ContentMode.manga;

  static ContentMode? parse(String? raw) {
    switch (raw?.trim()) {
      case 'manga':
        return ContentMode.manga;
      case 'novel':
        return ContentMode.novel;
      default:
        return null;
    }
  }

  String get wire => name;

  /// The switch's own label.
  String get label => this == ContentMode.novel ? 'Novels' : 'Manga';

  /// Used in empty states: "No novels in your library yet".
  String get plural => this == ContentMode.novel ? 'novels' : 'series';
}

/// The mode actually in force.
///
/// [novelsEnabled] is the production gate (`GET /auth/bootstrap-status`):
/// with it off there is exactly one mode and it is manga, whatever the
/// preferences hold.
ContentMode resolveContentMode(ContentMode? stored, {required bool novelsEnabled}) {
  if (!novelsEnabled) return ContentMode.fallback;
  return stored ?? ContentMode.fallback;
}

/// The kind a source serves. Anything unlabelled is manga — see invariant 1.
ContentMode sourceContentMode(SourceSummary? source) =>
    source?.contentKind == kNovelContentKind
        ? ContentMode.novel
        : ContentMode.manga;

/// `sourceId -> mode` for every installed source, built once from
/// `GET /sources`.
///
/// Rows elsewhere in the app (follows, notifications, history, bookmarks,
/// downloads) carry a source id but not a kind, so this index is how they get
/// scoped without a backend change or a new column.
Map<String, ContentMode> buildSourceModeIndex(Iterable<SourceSummary>? sources) {
  final index = <String, ContentMode>{};
  for (final source in sources ?? const <SourceSummary>[]) {
    index[source.id] = sourceContentMode(source);
  }
  return index;
}

/// Whether a row from [sourceId] belongs in [mode].
///
/// An UNKNOWN source id — one the listing does not carry, because the
/// connector was removed, is hidden by the 18+ gate, or the list has not
/// loaded yet — resolves to manga, so it keeps showing exactly where it shows
/// today and a slow `/sources` response cannot blank the library. The cost is
/// that an orphaned novel follow would appear in manga mode; the alternative
/// (hiding unknown rows) would flash the whole library empty on every cold
/// load, on a phone that is offline more often than the web ever is.
bool matchesContentMode(
  String? sourceId,
  Map<String, ContentMode> index,
  ContentMode mode,
) {
  if (sourceId == null) return mode == ContentMode.manga;
  return (index[sourceId] ?? ContentMode.manga) == mode;
}

/// Keep the rows of [mode], reading each row's source id with [sourceIdOf].
///
/// With novels disabled this returns [rows] **untouched** rather than
/// filtering to manga: identical output, but it also cannot be the thing that
/// broke a list if the index is ever wrong.
List<T> filterByContentMode<T>(
  List<T> rows,
  Map<String, ContentMode> index,
  ContentMode mode, {
  required String? Function(T row) sourceIdOf,
  required bool novelsEnabled,
}) {
  if (!novelsEnabled) return rows;
  return rows
      .where((row) => matchesContentMode(sourceIdOf(row), index, mode))
      .toList();
}

/// Keep the sources of [mode], straight off `content_kind` — no index needed,
/// this IS the index's input.
List<SourceSummary> filterSourcesByContentMode(
  List<SourceSummary> sources,
  ContentMode mode, {
  required bool novelsEnabled,
}) {
  if (!novelsEnabled) return sources;
  return sources.where((s) => sourceContentMode(s) == mode).toList();
}

/// Whether OCR search belongs in [mode].
///
/// OCR reads text recognised from chapter page IMAGES. A novel has no images
/// to recognise, so in Novels mode the screen could only ever be empty —
/// hiding the entry is more honest than showing a search box that can never
/// return anything.
bool isOcrVisible(ContentMode mode, {required bool novelsEnabled}) {
  if (!novelsEnabled) return true;
  return mode == ContentMode.manga;
}
