import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';

/// Wire models for source migration — repointing a follow at another source
/// while keeping the reader's place.
///
/// Shapes come from `backend/routes/updates.py:159-211` and
/// `backend/services/update_service.py:612-674` (candidates) /
/// `:684-790` (the plan). They mirror the web client's
/// `frontend/src/features/updates/types.ts:60-151` field for field, so the two
/// clients model one feature rather than two.

/// Somewhere a followed series could be moved to: the best hit for this title
/// on one *other* source.
///
/// The endpoint reuses the federated search fan-out and keeps only the top item
/// per source (`update_service.py:644-666`), so there is at most one candidate
/// per connector and every candidate's source answered *this* request.
class MigrationCandidate {
  const MigrationCandidate({
    required this.source,
    required this.seriesId,
    required this.title,
    this.sourceName,
    this.iconUrl,
    this.coverUrl,
    this.author,
    this.chapterCount,
  });

  /// Connector id — the tracker API's `source`.
  final String source;

  /// The connector's own id for the series.
  final String seriesId;
  final String title;
  final String? sourceName;
  final String? iconUrl;

  /// Absolute, backend-served cover URL — use as-is, no base-URL resolution
  /// (`browse_service.py:681-686` builds it with `_absolute_url`).
  final String? coverUrl;
  final String? author;

  /// Catalog size the source reported, or null when it did not say. Most search
  /// endpoints omit it, so null means "unknown", never "empty".
  final int? chapterCount;

  /// Display name, falling back to the raw connector id.
  String get displayName =>
      (sourceName == null || sourceName!.isEmpty) ? source : sourceName!;

  factory MigrationCandidate.fromJson(Map<String, dynamic> json) {
    final count = (json['chapter_count'] as num?)?.toInt();
    return MigrationCandidate(
      source: json['source'] as String? ?? '',
      seriesId: json['series_id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      sourceName: json['source_name'] as String?,
      iconUrl: json['icon_url'] as String?,
      coverUrl: json['cover_url'] as String?,
      author: json['author'] as String?,
      // The backend already normalises 0 to null; belt and braces here so a
      // literal 0 never renders as "0 chapters" (which reads as "empty").
      chapterCount: (count == null || count <= 0) ? null : count,
    );
  }
}

/// `GET /updates/trackers/{id}/migration-candidates`.
class MigrationCandidateList {
  const MigrationCandidateList({
    required this.tracker,
    required this.query,
    required this.candidates,
    required this.sourcesQueried,
    required this.sourcesFailed,
  });

  final SeriesTracker tracker;

  /// The query actually used — defaults to the followed title server-side.
  final String query;

  /// Server order, preserved verbatim: relevance-ranked with sources on a
  /// failure streak demoted (`browse_service.py:805-812`).
  final List<MigrationCandidate> candidates;

  final int sourcesQueried;

  /// How many sources did not answer. Routinely large on a registry of ~151
  /// connectors, roughly two thirds of which are dead — this is normal
  /// partial-failure reporting, not an error.
  final int sourcesFailed;

  factory MigrationCandidateList.fromJson(Map<String, dynamic> json) =>
      MigrationCandidateList(
        tracker: SeriesTracker.fromJson(
          json['tracker'] as Map<String, dynamic>,
        ),
        query: json['query'] as String? ?? '',
        candidates: (json['candidates'] as List<dynamic>? ?? const [])
            .map((e) => MigrationCandidate.fromJson(e as Map<String, dynamic>))
            .toList(),
        sourcesQueried: (json['sources_queried'] as num?)?.toInt() ?? 0,
        sourcesFailed: (json['sources_failed'] as num?)?.toInt() ?? 0,
      );
}

/// How one old chapter found its counterpart on the target.
///
/// Chapters are matched by NUMBER: ids are opaque per-source strings and titles
/// are translations, so the number is the only axis comparable across sources
/// (`update_service.py:142-159`). [nearest] matched a lower-numbered chapter
/// within tolerance; [none] found nothing and carries no progress.
enum ChapterMatch {
  exact,
  nearest,
  none;

  static ChapterMatch parse(String? raw) => switch (raw) {
        'exact' => ChapterMatch.exact,
        'nearest' => ChapterMatch.nearest,
        _ => ChapterMatch.none,
      };
}

/// One old chapter's fate under the proposed remap.
class ChapterMapEntry {
  const ChapterMapEntry({
    required this.fromChapterId,
    required this.number,
    required this.toChapterId,
    required this.match,
  });

  final String fromChapterId;

  /// Chapter number on the old source; null when the source left it unnumbered,
  /// which is exactly the case that cannot be matched.
  final double? number;

  /// Target chapter id, or null when nothing on the target corresponds.
  final String? toChapterId;
  final ChapterMatch match;

  bool get carriesOver => toChapterId != null && toChapterId!.isNotEmpty;

  factory ChapterMapEntry.fromJson(Map<String, dynamic> json) {
    final to = json['to_chapter_id'] as String?;
    return ChapterMapEntry(
      fromChapterId: json['from_chapter_id'] as String? ?? '',
      number: (json['number'] as num?)?.toDouble(),
      toChapterId: (to == null || to.isEmpty) ? null : to,
      match: ChapterMatch.parse(json['match'] as String?),
    );
  }
}

/// Chapter tallies for the proposed move.
class MigrationCounts {
  const MigrationCounts({
    required this.oldTotal,
    required this.newTotal,
    required this.matched,
    required this.dropped,
  });

  /// Wire `counts.old` — chapters known on the source being left.
  final int oldTotal;

  /// Wire `counts.new` — chapters the target lists.
  final int newTotal;

  /// Old chapters that found a counterpart.
  final int matched;

  /// Old chapters with no equivalent; their progress cannot come along.
  final int dropped;

  factory MigrationCounts.fromJson(Map<String, dynamic> json) =>
      MigrationCounts(
        oldTotal: (json['old'] as num?)?.toInt() ?? 0,
        newTotal: (json['new'] as num?)?.toInt() ?? 0,
        matched: (json['matched'] as num?)?.toInt() ?? 0,
        dropped: (json['dropped'] as num?)?.toInt() ?? 0,
      );
}

/// Whether the source being left could still be read when the plan was built.
///
/// A dead old source is the whole reason this feature exists, so its catalog is
/// best-effort (`update_service.py:713-721`): [cached] means the remap was
/// computed from the chapter numbers recorded at the last successful update
/// check, [unavailable] means not even those existed.
enum OldCatalogState {
  ok,
  cached,
  unavailable;

  static OldCatalogState parse(String? raw) => switch (raw) {
        'ok' => OldCatalogState.ok,
        'cached' => OldCatalogState.cached,
        _ => OldCatalogState.unavailable,
      };
}

/// Another tracker for the same series on the source being left — typically the
/// *downloaded* twin, which cannot be migrated (`update_service.py:799-809`)
/// because `sync-downloaded` would just recreate it at the old source.
class MigrationSiblingTracker {
  const MigrationSiblingTracker({required this.id, required this.trackKind});

  final int id;
  final TrackKind trackKind;

  factory MigrationSiblingTracker.fromJson(Map<String, dynamic> json) =>
      MigrationSiblingTracker(
        id: (json['id'] as num).toInt(),
        trackKind: json['track_kind'] == 'downloaded'
            ? TrackKind.downloaded
            : TrackKind.followed,
      );
}

/// The result of `POST /updates/trackers/{id}/migrate`.
///
/// Preview (`dry_run`) and commit return the identical shape and are computed
/// by the same code path (`update_service.py:820-920`); [applied] says which
/// happened. That shared path is what makes the preview trustworthy: the map
/// the user confirms is built exactly the way the map they were shown was.
class MigrationPlan {
  const MigrationPlan({
    required this.trackerId,
    required this.fromSource,
    required this.fromSeriesId,
    required this.toSource,
    required this.toSeriesId,
    required this.oldCatalog,
    required this.chapterMap,
    required this.counts,
    required this.chapterMapHash,
    required this.applied,
    this.warnings = const [],
    this.siblingTrackers = const [],
    this.unmatchedSourceChapters = const [],
    this.targetOnlyChapters = const [],
    this.notificationsRewritten = 0,
    this.notificationsDropped = 0,
    this.downloadsRelinked = 0,
    this.mergedIntoTrackerId,
  });

  final int trackerId;
  final String fromSource;
  final String fromSeriesId;
  final String toSource;
  final String toSeriesId;
  final OldCatalogState oldCatalog;

  /// The remap the client replays over its own online-progress store. Reading
  /// progress for a non-downloaded remote series exists ONLY on the client, so
  /// the server cannot move it (`routes/updates.py:195-201`).
  final List<ChapterMapEntry> chapterMap;

  final MigrationCounts counts;

  /// Sent back on commit so a target whose chapter list changed since the
  /// preview is refused (409 `migration_stale`) rather than silently applied.
  final String chapterMapHash;

  /// True only for a real migration; false for every dry run.
  final bool applied;

  /// Server-authored prose about what will be lost. Rendered verbatim — these
  /// sentences name the sources and counts involved.
  final List<String> warnings;

  final List<MigrationSiblingTracker> siblingTrackers;
  final List<String> unmatchedSourceChapters;
  final List<String> targetOnlyChapters;

  final int notificationsRewritten;
  final int notificationsDropped;
  final int downloadsRelinked;

  /// Set when the commit folded this follow into an existing one (merge).
  final int? mergedIntoTrackerId;

  /// `from_chapter_id` -> `to_chapter_id` for every chapter that carries over.
  /// The shape the client-side progress remap consumes.
  Map<String, String> get carriedChapterIds => {
        for (final entry in chapterMap)
          if (entry.carriesOver) entry.fromChapterId: entry.toChapterId!,
      };

  factory MigrationPlan.fromJson(Map<String, dynamic> json) {
    final from = json['from'] as Map<String, dynamic>? ?? const {};
    final to = json['to'] as Map<String, dynamic>? ?? const {};
    return MigrationPlan(
      trackerId: (json['tracker_id'] as num?)?.toInt() ?? 0,
      fromSource: from['source'] as String? ?? '',
      fromSeriesId: from['series_id'] as String? ?? '',
      toSource: to['source'] as String? ?? '',
      toSeriesId: to['series_id'] as String? ?? '',
      oldCatalog: OldCatalogState.parse(json['old_catalog'] as String?),
      chapterMap: (json['chapter_map'] as List<dynamic>? ?? const [])
          .map((e) => ChapterMapEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
      counts: MigrationCounts.fromJson(
        json['counts'] as Map<String, dynamic>? ?? const {},
      ),
      chapterMapHash: json['chapter_map_hash'] as String? ?? '',
      applied: json['applied'] as bool? ?? false,
      warnings: [
        for (final warning in json['warnings'] as List<dynamic>? ?? const [])
          warning as String,
      ],
      siblingTrackers:
          (json['sibling_trackers'] as List<dynamic>? ?? const [])
              .map(
                (e) => MigrationSiblingTracker.fromJson(
                  e as Map<String, dynamic>,
                ),
              )
              .toList(),
      unmatchedSourceChapters: [
        for (final id
            in json['unmatched_source_chapters'] as List<dynamic>? ?? const [])
          id as String,
      ],
      targetOnlyChapters: [
        for (final id in json['target_only_chapters'] as List<dynamic>? ?? const [])
          id as String,
      ],
      notificationsRewritten:
          (json['notifications_rewritten'] as num?)?.toInt() ?? 0,
      notificationsDropped: (json['notifications_dropped'] as num?)?.toInt() ?? 0,
      downloadsRelinked: (json['downloads_relinked'] as num?)?.toInt() ?? 0,
      mergedIntoTrackerId: (json['merged_into_tracker_id'] as num?)?.toInt(),
    );
  }
}
