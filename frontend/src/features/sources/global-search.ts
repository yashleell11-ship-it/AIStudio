import type { GlobalSearchItem } from "./types";

/**
 * Route a federated search hit to its detail page:
 * - `local`  → the local library series route `/library/{series_id}`.
 * - `source` → the source series route
 *   `/sources/{source}/series/{encodeURIComponent(series_id)}`.
 *
 * `series_id` is used verbatim for local ids (numeric strings) and
 * percent-encoded for source ids, which may contain slashes or other unsafe
 * path characters.
 */
export function globalSearchHref(item: GlobalSearchItem): string {
  if (item.kind === "local") {
    return `/library/${item.series_id}`;
  }
  return `/sources/${item.source}/series/${encodeURIComponent(item.series_id)}`;
}

/**
 * Human summary of how wide a federated search reached, e.g.
 * `"Searched 5 sources"` or `"Searched 5 sources (2 failed)"`. Returns null when
 * no sources were queried, so callers can omit the line entirely.
 */
export function globalSearchScopeLabel(
  sourcesQueried: number,
  sourcesFailed: number,
): string | null {
  if (sourcesQueried <= 0) {
    return null;
  }
  const noun = sourcesQueried === 1 ? "source" : "sources";
  const base = `Searched ${sourcesQueried} ${noun}`;
  return sourcesFailed > 0 ? `${base} (${sourcesFailed} failed)` : base;
}
