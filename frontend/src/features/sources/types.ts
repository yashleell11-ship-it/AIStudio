/** Connector reachability, as last observed by the server. */
export interface SourceHealth {
  status: string;
  consecutive_failures: number;
  demoted: boolean;
  last_ok_at: string | null;
  last_error_at: string | null;
  last_error: string | null;
  last_checked_at: string | null;
}

export interface SourceSummary {
  id: string;
  name: string;
  description: string;
  browsable: boolean;
  supports_import: boolean;
  icon_url?: string | null;
  /**
   * 18+ connector. `GET /sources` has always carried this — the web type just
   * never modelled it, which is why the web listing had no way to badge or
   * filter adult sources while the mobile one did.
   */
  mature?: boolean;
  health?: SourceHealth | null;
}

/**
 * A pinned source as returned by `GET`/`PUT /sources/pins`.
 *
 * Pins live on the server and are scoped to `(user_id, profile_id)`, so they
 * follow the account across devices and never leak between profiles.
 * `source_id` is a connector key, not a foreign key: a connector can be
 * removed, renamed, or hidden by the 18+ gate, in which case the pin is still
 * returned with `available: false` rather than silently vanishing from the
 * user's ordering.
 */
export interface SourcePin {
  source_id: string;
  /** 0-based and dense — identical to the position in the pins array. */
  sort_order: number;
  /** Connector display name; falls back to `source_id` when unresolvable. */
  name: string;
  icon_url: string | null;
  mature: boolean;
  /** False when `source_id` no longer resolves to a source this profile sees. */
  available: boolean;
}

export interface SourceSeriesSummary {
  id: string;
  source_id: string;
  title: string;
  chapter_count: number;
  description: string | null;
  author: string | null;
  artist: string | null;
  status: string | null;
  genres: string[];
  latest_chapter: string | null;
  cover_url: string;
}

export type SourceSeriesDetail = SourceSeriesSummary;

export interface SourceChapterSummary {
  id: string;
  source_id: string;
  series_id: string;
  title: string;
  number: number | null;
  page_count: number;
  release_date: string | null;
}

export interface PaginatedSourceSeries {
  items: SourceSeriesSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_more: boolean;
}

export interface SourceBrowseMode {
  id: string;
  label: string;
}

export type SourceGenre = SourceBrowseMode;

/**
 * A single hit from the federated `GET /sources/search` endpoint, which merges
 * the local library and every enabled remote source into one feed.
 *
 * `series_id` is always a STRING (local ids are numeric strings, source ids are
 * opaque source-defined strings) and `cover_url` is already an ABSOLUTE URL, so
 * it is consumed verbatim — never run through a cover-url helper.
 */
export interface GlobalSearchItem {
  /** `"local"` for a library series, `"source"` for a remote source series. */
  kind: "local" | "source";
  /** Source id (e.g. `mangadex`) when `kind === "source"`; null for local. */
  source: string | null;
  series_id: string;
  title: string;
  /** Absolute cover URL served by the backend; use directly. */
  cover_url: string | null;
  author: string | null;
  /**
   * Catalog size as the source reported it, on source hits only. `0` means
   * "the source did not say" — most search endpoints omit it — not "empty".
   */
  chapter_count?: number | null;
  extra: Record<string, unknown> | null;
}

/**
 * `ok` — the source answered with hits. `empty` — it answered with nothing (or
 * with results the backend discarded as unrelated to the query, in which case
 * `error` carries the explanation). `error` — it did not answer.
 */
export type GlobalSearchGroupStatus = "ok" | "empty" | "error";

/**
 * One section of `GET /sources/search`: the local library plus one entry per
 * queried source.
 *
 * Ordering is decided server-side and must be preserved verbatim — `groups[0]`
 * is the local library, then sources best-relevance-first with empty and failed
 * ones sinking to the bottom. Items inside a group are already best-match-first.
 */
export interface GlobalSearchGroup {
  /** Connector id, or `null` — which is what identifies the local library. */
  source: string | null;
  source_name: string;
  icon_url: string | null;
  status: GlobalSearchGroupStatus;
  /** Always set on `error`; also set on an `empty` group the backend ignored. */
  error: string | null;
  total: number;
  has_more: boolean;
  items: GlobalSearchItem[];
}

export interface GlobalSearchResponse {
  /**
   * Flat, round-robin-interleaved view of `groups`, kept by the backend for
   * older clients. The web renders `groups`.
   */
  items: GlobalSearchItem[];
  groups: GlobalSearchGroup[];
  sources_queried: number;
  sources_failed: number;
  page: number;
  has_more: boolean;
}
