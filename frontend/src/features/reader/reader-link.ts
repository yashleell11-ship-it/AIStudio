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

/** The source series page for a `(source, series_key)`. */
export function seriesPageHref(ref: SeriesId): string {
  return `/sources/${encodeURIComponent(ref.sourceId)}/series/${encodeURIComponent(
    ref.seriesKey,
  )}`;
}
