/**
 * Source-native library types (spec §2, §3.4).
 *
 * The library is the per-profile set of `followed_series` rows. A series is
 * `(source_id, series_key)`; a chapter is `(source_id, series_key,
 * chapter_key)`. There is no local catalog, no `library_id`, no integer series
 * id for domain identity — `followed_id` is only a handle for follow-row
 * mutations (`PATCH`/`DELETE /library/...`).
 */

import type { SeriesId } from "@/types/api";

export type { SeriesId };

/** One entry in a followed series' known-chapter snapshot / live chapter list. */
export interface KnownChapter {
  key: string;
  number: number | null;
  title: string | null;
  published_at: string | null;
  /** Only present on the cache-backed detail chapter list. */
  page_count?: number | null;
}

/**
 * A followed series as returned by `GET /library/series` items and
 * `POST /library/follow` (backend `FollowedSeriesService.serialize`).
 */
export interface FollowedSeries {
  /** `followed_id` — the follow row's PK. Use for PATCH/DELETE, never routing. */
  id: number;
  source_id: string;
  series_key: string;
  title: string;
  /**
   * Ready-to-use cover URL. The backend returns either the source's own
   * absolute URL or a backend-relative `/sources/{source}/series/{series}/cover`
   * proxy path — resolve the relative form against the API base with
   * `libraryCoverUrl`.
   */
  cover_url: string;
  is_favorite: boolean;
  reading_status: string;
  notify: boolean;
  sort_order: number;
  content_rating: string;
  /** Effective rating after gate/override resolution ("mature" | "safe" | ...). */
  rating: string;
  mature_override: boolean | null;
  known_chapters: KnownChapter[];
  chapter_count: number;
  last_checked_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** `GET /library/series` — paginated followed-series list. */
export interface SeriesListResponse {
  items: FollowedSeries[];
  total: number;
  page: number;
  per_page: number;
  page_size: number;
  has_next: boolean;
  has_more: boolean;
  total_pages: number;
}

/** Per-chapter reading position overlaid on the detail payload. */
export interface ChapterProgressEntry {
  last_page: number;
  is_completed: boolean;
}

/**
 * `GET /library/series/{followed_id}` — the follow row plus cache meta, the
 * live chapter list, and a `chapter_key -> progress` overlay.
 */
export interface SeriesDetail extends FollowedSeries {
  description: string | null;
  author: string | null;
  genres: string[] | null;
  chapters: KnownChapter[];
  progress: Record<string, ChapterProgressEntry>;
}

/**
 * `POST` / `DELETE /library/follow` outcome — the follow row after the write,
 * or `null` once unfollowed.
 */
export type FollowMutationResult = FollowedSeries | null;

/** `GET /library/continue-reading` item (progress-service shape). */
export interface ContinueReadingItem {
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number: number | null;
  last_page: number;
  page_count: number;
  last_read_at: string | null;
}

/**
 * The `sort` values `GET /library/series` understands
 * (`FollowedSeriesService.list_series`). A leading `-` reverses.
 */
export type SeriesSort =
  | "title"
  | "sort_title"
  | "sort_order"
  | "updated_at"
  | "recently_updated"
  | "created_at"
  | "recently_added";

/** Reading-status filter used by the toolbar. `all` is the client-only default. */
export type SeriesFilter = "all" | "unread" | "reading" | "completed" | "on_hold" | "plan_to_read" | "dropped";

// --- Collections ---

export interface Collection {
  id: number;
  name: string;
  description: string | null;
  cover_url: string | null;
  sort_order: number;
  series_count: number;
}

export interface CollectionRef {
  id: number;
  name: string;
}

export interface CollectionSeriesRef {
  source_id: string;
  series_key: string;
  sort_order: number;
}

export interface CollectionDetail extends Collection {
  series: CollectionSeriesRef[];
}

// --- Tags ---

export interface Tag {
  id: number;
  name: string;
  category: string;
  color: string | null;
}

// --- Search ---

export type SearchResponse = SeriesListResponse;

// --- Recommendations ---

/** `GET /library/recommendations` — top genres over the followed set. */
export interface RecommendationGenre {
  genre: string;
  weight: number;
}

export type RecommendationsResponse = RecommendationGenre[];

// --- Reading history ---

/** `GET /reader/history` row (progress-service `_serialize`). */
export interface ReadingHistoryItem {
  id: number;
  source_id: string;
  series_key: string;
  chapter_key: string;
  chapter_number: number | null;
  last_page: number;
  page_count: number;
  scroll_offset_px: number;
  is_completed: boolean;
  started_at: string | null;
  last_read_at: string | null;
  completed_at: string | null;
  time_spent_seconds: number;
}

// --- Statistics ---

/** `GET /library/statistics` (`FollowedSeriesService.statistics`). */
export interface Statistics {
  followed_total: number;
  favorites: number;
  by_reading_status: Record<string, number>;
  chapters_completed: number;
}

// --- Bookmarks ---

export interface Bookmark {
  id: number;
  source_id: string;
  series_key: string;
  chapter_key: string;
  page: number;
  note: string | null;
  created_at: string | null;
}
