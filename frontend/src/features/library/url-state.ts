import type { SeriesFilter, SeriesSort } from "./types";

/**
 * The library view's filter/sort state, as it lives in the query string.
 *
 * Source-native (spec §3.4): the library is the per-profile `followed_series`
 * set, so `GET /library/series` only accepts `search`, `sort`, `reading_status`
 * and `is_favorite`. The old catalog filters (`library_id`, `has_chapters`,
 * `language`, `collection_id`, `tag_id`) are gone.
 */
export interface LibraryQuery {
  search: string;
  sort: SeriesSort;
  /** Client-only convenience alias folded into `reading_status` on the wire. */
  status: SeriesFilter;
  /** Shelf status on the follow row. */
  reading_status: string | null;
  is_favorite: boolean | null;
}

/**
 * Sort values `FollowedSeriesService.list_series` branches on. A leading `-`
 * reverses; anything unrecognised sorts by title, so it is folded to `title`.
 */
const SORTS: readonly SeriesSort[] = [
  "title",
  "sort_title",
  "sort_order",
  "updated_at",
  "recently_updated",
  "created_at",
  "recently_added",
];

/** Reading-status values the backend accepts (`READING_STATUSES`). */
export const READING_STATUSES = [
  "unread",
  "reading",
  "completed",
  "on_hold",
  "plan_to_read",
  "dropped",
] as const;

export type ReadingStatus = (typeof READING_STATUSES)[number];

/** The client-only status chips; `all` clears the filter. */
const STATUSES: readonly SeriesFilter[] = [
  "all",
  "unread",
  "reading",
  "completed",
  "on_hold",
  "plan_to_read",
  "dropped",
];

/**
 * The view's own default: newest-updated first. It is the value omitted from
 * the query string.
 */
export const DEFAULT_LIBRARY_QUERY: LibraryQuery = {
  search: "",
  sort: "recently_updated",
  status: "all",
  reading_status: null,
  is_favorite: null,
};

/** Just enough of `URLSearchParams` to read: also satisfied by Next's readonly one. */
export interface QueryParamSource {
  get(name: string): string | null;
}

function isMember<T extends string>(allowed: readonly T[], raw: string | null): raw is T {
  return raw !== null && (allowed as readonly string[]).includes(raw);
}

function parseEnum<T extends string>(
  allowed: readonly T[],
  raw: string | null,
  fallback: T,
): T {
  return isMember(allowed, raw) ? raw : fallback;
}

function parseOptionalEnum<T extends string>(
  allowed: readonly T[],
  raw: string | null,
): T | null {
  return isMember(allowed, raw) ? raw : null;
}

function parseBoolean(raw: string | null): boolean | null {
  if (raw === "true" || raw === "1") return true;
  if (raw === "false" || raw === "0") return false;
  return null;
}

/**
 * Read a view state out of a query string. Never throws and never yields a
 * value the backend would reject.
 */
export function parseLibraryQuery(params: QueryParamSource): LibraryQuery {
  return {
    search: params.get("search")?.trim() ?? DEFAULT_LIBRARY_QUERY.search,
    sort: parseEnum(SORTS, params.get("sort"), DEFAULT_LIBRARY_QUERY.sort),
    status: parseEnum(STATUSES, params.get("status"), DEFAULT_LIBRARY_QUERY.status),
    reading_status: parseOptionalEnum(READING_STATUSES, params.get("reading_status")),
    is_favorite: parseBoolean(params.get("is_favorite")),
  };
}

/** Serialize, omitting everything at its default. Key order is fixed. */
export function libraryQueryToSearchParams(query: LibraryQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.sort !== DEFAULT_LIBRARY_QUERY.sort) params.set("sort", query.sort);
  if (query.status !== "all") params.set("status", query.status);
  if (query.reading_status) params.set("reading_status", query.reading_status);
  if (query.is_favorite !== null) params.set("is_favorite", String(query.is_favorite));
  return params;
}

/** `?a=b`, or `""` for the default view so the bare path stays clean. */
export function libraryQuerySearchString(query: LibraryQuery): string {
  const serialized = libraryQueryToSearchParams(query).toString();
  return serialized.length > 0 ? `?${serialized}` : "";
}

export function isDefaultLibraryQuery(query: LibraryQuery): boolean {
  return libraryQueryToSearchParams(query).toString().length === 0;
}

/** True when anything narrows the grid — drives which empty state to show. */
export function hasActiveFilters(query: LibraryQuery): boolean {
  return (
    query.status !== "all" ||
    query.reading_status !== null ||
    query.is_favorite !== null
  );
}

export interface SeriesListParams {
  page: number;
  per_page: number;
  sort: SeriesSort;
  search?: string;
  status?: SeriesFilter;
  reading_status?: string;
  is_favorite?: boolean;
}

/** The `GET /library/series` arguments for a view state. */
export function libraryQueryToListParams(
  query: LibraryQuery,
  paging: { page: number; per_page: number },
): SeriesListParams {
  return {
    page: paging.page,
    per_page: paging.per_page,
    sort: query.sort,
    search: query.search.trim() || undefined,
    status: query.status !== "all" ? query.status : undefined,
    reading_status: query.reading_status ?? undefined,
    is_favorite: query.is_favorite ?? undefined,
  };
}
