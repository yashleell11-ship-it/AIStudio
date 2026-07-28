import type { SeriesFilter, SeriesSort } from "./types";

/**
 * The library view's filter/sort state, as it lives in the query string.
 *
 * Field names are the WIRE names `GET /library/series` accepts
 * (backend/routes/library.py:144-159, backend/services/library_service.py:548-637)
 * rather than prettier camelCase ones: the query string, this object and the
 * request all use one vocabulary, so there is no translation layer for a typo to
 * hide in and a URL says exactly which server-side filter it turns on.
 *
 * `page`/`per_page` are deliberately absent — the view loads one large page and
 * has no paging control, so putting them in the URL would promise a back-button
 * behaviour nothing implements.
 */
export interface LibraryQuery {
  search: string;
  sort: SeriesSort;
  /** Progress-derived filter: joins ReadingProgress server-side. */
  status: SeriesFilter;
  /** The caller's own shelf status on `user_series_state`. */
  reading_status: string | null;
  is_favorite: boolean | null;
  language: string | null;
  has_chapters: boolean | null;
  collection_id: number | null;
  tag_id: number | null;
  library_id: number | null;
}

/**
 * Sort values `list_series` actually branches on, plus `sort_title` — the
 * route's own default and what its `else` branch does
 * (backend/services/library_service.py:636-637). Anything else silently sorts by
 * title server-side, so it is folded to `sort_title` here instead of being
 * echoed back into the URL as if it meant something.
 */
const SORTS: readonly SeriesSort[] = [
  "sort_title",
  "updated",
  "recent",
  "date_added",
  "author",
  "year",
  "total_chapters",
];

/** `list_series` only branches on these two; anything else means "no filter". */
const STATUSES: readonly SeriesFilter[] = ["all", "reading", "unread"];

/**
 * The shelf statuses the backend ever writes: the column default plus what
 * `get_statistics` counts (backend/services/library_intelligence_service.py:1297-1301).
 * Cards style a couple of others defensively, but nothing produces them.
 */
export const READING_STATUSES = ["unread", "reading", "completed"] as const;

export type ReadingStatus = (typeof READING_STATUSES)[number];

/**
 * The view's own default, not the route's: the grid has always opened on
 * "Recently Updated" and a URL feature must not quietly re-sort everyone's
 * library. It is the value omitted from the query string.
 */
export const DEFAULT_LIBRARY_QUERY: LibraryQuery = {
  search: "",
  sort: "updated",
  status: "all",
  reading_status: null,
  is_favorite: null,
  language: null,
  has_chapters: null,
  collection_id: null,
  tag_id: null,
  library_id: null,
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

/** An unrecognised value clears the filter rather than being sent on to a 422. */
function parseOptionalEnum<T extends string>(
  allowed: readonly T[],
  raw: string | null,
): T | null {
  return isMember(allowed, raw) ? raw : null;
}

/** FastAPI accepts these for a `bool | None` query param; so do we. */
function parseBoolean(raw: string | null): boolean | null {
  if (raw === "true" || raw === "1") return true;
  if (raw === "false" || raw === "0") return false;
  return null;
}

/** Ids are positive integers; a junk value is no filter rather than a 422. */
function parseId(raw: string | null): number | null {
  if (raw === null) return null;
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

function parseText(raw: string | null): string | null {
  const trimmed = raw?.trim() ?? "";
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * Read a view state out of a query string. Never throws and never yields a
 * value the backend would reject — a hand-edited or truncated URL degrades to
 * the default view rather than to an error page.
 */
export function parseLibraryQuery(params: QueryParamSource): LibraryQuery {
  return {
    search: params.get("search")?.trim() ?? DEFAULT_LIBRARY_QUERY.search,
    sort: parseEnum(SORTS, params.get("sort"), DEFAULT_LIBRARY_QUERY.sort),
    status: parseEnum(STATUSES, params.get("status"), DEFAULT_LIBRARY_QUERY.status),
    reading_status: parseOptionalEnum(READING_STATUSES, params.get("reading_status")),
    is_favorite: parseBoolean(params.get("is_favorite")),
    language: parseText(params.get("language")),
    has_chapters: parseBoolean(params.get("has_chapters")),
    collection_id: parseId(params.get("collection_id")),
    tag_id: parseId(params.get("tag_id")),
    library_id: parseId(params.get("library_id")),
  };
}

/**
 * Serialize, omitting everything at its default.
 *
 * Key order is fixed rather than insertion-dependent so the same view always
 * produces byte-identical URLs: a differing string would push a duplicate
 * history entry and make the back button feel broken.
 */
export function libraryQueryToSearchParams(query: LibraryQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.search.trim()) params.set("search", query.search.trim());
  if (query.sort !== DEFAULT_LIBRARY_QUERY.sort) params.set("sort", query.sort);
  if (query.status !== "all") params.set("status", query.status);
  if (query.reading_status) params.set("reading_status", query.reading_status);
  if (query.is_favorite !== null) params.set("is_favorite", String(query.is_favorite));
  if (query.language) params.set("language", query.language);
  if (query.has_chapters !== null) params.set("has_chapters", String(query.has_chapters));
  if (query.collection_id !== null) params.set("collection_id", String(query.collection_id));
  if (query.tag_id !== null) params.set("tag_id", String(query.tag_id));
  if (query.library_id !== null) params.set("library_id", String(query.library_id));
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
    query.is_favorite !== null ||
    query.language !== null ||
    query.has_chapters !== null ||
    query.collection_id !== null ||
    query.tag_id !== null ||
    query.library_id !== null
  );
}

export interface SeriesListParams {
  page: number;
  per_page: number;
  sort: SeriesSort;
  search?: string;
  status?: SeriesFilter;
  reading_status?: string;
  collection_id?: number;
  tag_id?: number;
  library_id?: number;
  is_favorite?: boolean;
  language?: string;
  has_chapters?: boolean;
}

/**
 * The `GET /library/series` arguments for a view state. Nulls become absent
 * params: the backend treats "absent" and "no filter" as the same thing, and
 * sending `is_favorite=null` would be a 422.
 */
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
    collection_id: query.collection_id ?? undefined,
    tag_id: query.tag_id ?? undefined,
    library_id: query.library_id ?? undefined,
    is_favorite: query.is_favorite ?? undefined,
    language: query.language ?? undefined,
    has_chapters: query.has_chapters ?? undefined,
  };
}
