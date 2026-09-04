import { encodePathKey } from "@/services/http";
import type { ChapterId, SeriesId } from "@/types/api";

/**
 * The unified reader route (spec §3.3, O-1): path segments, every one
 * `encodeURIComponent`-encoded, with the chapter key as a `[...chapterKey]`
 * catch-all so opaque keys containing `/` survive.
 */
export function readerChapterHref(ref: ChapterId, page?: number): string {
  const base = `/reader/${encodeURIComponent(ref.sourceId)}/${encodeURIComponent(
    ref.seriesKey,
  )}/${encodePathKey(ref.chapterKey)}`;
  return page && page > 1 ? `${base}?page=${page}` : base;
}

/**
 * The Read-all route: the whole series as one scroll (spec 2026-09-05 R2).
 *
 * A route of its own rather than a flag on the chapter reader, for the reason
 * every route here is its own route: `/reader/<source>/<series>/<...chapter>`
 * ends in an OPAQUE catch-all, so any marker put there could equally be a real
 * chapter whose key happens to be that word. `from` is a query parameter for
 * the same reason it is a query parameter everywhere else — chapter keys
 * contain slashes, and `URLSearchParams` encodes them safely.
 */
export function readAllHref(ref: SeriesId, fromChapterKey?: string | null): string {
  const base = `/read-all/${encodeURIComponent(ref.sourceId)}/${encodeURIComponent(
    ref.seriesKey,
  )}`;
  if (!fromChapterKey) return base;
  return `${base}?${new URLSearchParams({ from: fromChapterKey }).toString()}`;
}

/** The source series page for a `(source, series_key)`. */
export function seriesPageHref(ref: SeriesId): string {
  return `/sources/${encodeURIComponent(ref.sourceId)}/series/${encodeURIComponent(
    ref.seriesKey,
  )}`;
}
