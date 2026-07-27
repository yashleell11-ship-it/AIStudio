export interface SourceSummary {
  id: string;
  name: string;
  description: string;
  browsable: boolean;
  supports_import: boolean;
  icon_url?: string | null;
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
  extra: Record<string, unknown> | null;
}

export interface GlobalSearchResponse {
  items: GlobalSearchItem[];
  sources_queried: number;
  sources_failed: number;
  page: number;
  has_more: boolean;
}
