export type TrackKind = "followed" | "downloaded";

export interface UpdateSettings {
  enabled: boolean;
  check_interval_minutes: number;
  notify_enabled: boolean;
  auto_download_enabled: boolean;
  check_on_startup: boolean;
  last_run_at: string | null;
  updated_at: string | null;
}

export interface SeriesTracker {
  id: number;
  source: string;
  series_id: string;
  series_title: string;
  track_kind: TrackKind;
  local_series_id: number | null;
  enabled: boolean;
  notify: boolean;
  auto_download: boolean;
  check_interval_minutes: number | null;
  known_chapter_count: number;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface UpdateNotification {
  id: number;
  tracker_id: number;
  source: string;
  series_id: string;
  series_title: string;
  chapter_id: string;
  chapter_title: string;
  chapter_number: number | null;
  is_read: boolean;
  created_at: string | null;
}

export interface UpdateRun {
  id: number;
  trigger: string;
  status: string;
  series_checked: number;
  new_chapters_found: number;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface UpdateSource {
  source_type: string;
  name: string;
}

// --- Source migration ---

/**
 * Somewhere a followed series could be moved to: the best hit for this title on
 * one other source. The endpoint reuses the federated search fan-out, so a
 * large `sources_failed` is normal on a registry this size, not an error.
 */
export interface MigrationCandidate {
  source: string;
  source_name: string | null;
  icon_url: string | null;
  series_id: string;
  title: string;
  /** Absolute cover URL served by the backend; use directly. */
  cover_url: string | null;
  author: string | null;
  /** Catalog size the source reported, or null when it did not say. */
  chapter_count: number | null;
}

export interface MigrationCandidatesResponse {
  tracker: SeriesTracker;
  /** The query actually used — defaults to the followed title. */
  query: string;
  candidates: MigrationCandidate[];
  sources_queried: number;
  sources_failed: number;
}

/**
 * One old chapter's fate. Chapters are matched by NUMBER: ids are opaque
 * per-source strings and titles are translations, so the number is the only
 * stable axis. `nearest` matched a lower-numbered chapter within tolerance.
 */
export interface ChapterMapEntry {
  from_chapter_id: string;
  number: number | null;
  to_chapter_id: string | null;
  match: "exact" | "nearest" | "none";
}

export interface MigrationCounts {
  old: number;
  new: number;
  matched: number;
  dropped: number;
}

/**
 * The result of `POST /updates/trackers/{id}/migrate`. Preview (`dry_run`) and
 * commit return the identical shape and are computed by the same code path;
 * `applied` says which happened.
 */
export interface MigrationPlan {
  tracker_id: number;
  from: { source: string; series_id: string };
  to: { source: string; series_id: string };
  /**
   * `ok` — the source being left was readable. `cached` — it was not, so the
   * remap came from the chapter numbers recorded at the last successful check.
   * `unavailable` — neither, so nothing can be remapped.
   */
  old_catalog: "ok" | "cached" | "unavailable";
  /** The remap the client replays over its own online-progress store. */
  chapter_map: ChapterMapEntry[];
  unmatched_source_chapters: string[];
  target_only_chapters: string[];
  counts: MigrationCounts;
  /** Sent back on commit so a target that changed since the preview is refused. */
  chapter_map_hash: string;
  warnings: string[];
  sibling_trackers: { id: number; track_kind: TrackKind }[];
  notifications_rewritten: number;
  notifications_dropped: number;
  downloads_relinked: number;
  merged_into_tracker_id: number | null;
  applied: boolean;
}

export interface MigrateTrackerRequest {
  target_source: string;
  target_series_id: string;
  target_series_title?: string | null;
  /** Added to every old chapter number before matching (per-season restarts). */
  chapter_offset?: number;
  /** Defaults to a preview server-side; nothing is written unless false. */
  dry_run?: boolean;
  /** Only meaningful after a `tracker_target_already_followed` conflict. */
  merge?: boolean;
  /** From the preceding dry run; a changed target is refused rather than applied. */
  expected_chapter_map_hash?: string | null;
}
