/**
 * Where the chapter you are reading came from.
 *
 * A chapter knows its own series, so the reader never has to rely on history to
 * get there: arriving from search, Updates, a notification or a deep link all
 * leave the browser's back stack pointing somewhere else entirely.
 */
export type ChapterSeries =
  | { scope: "local"; seriesId: number }
  | { scope: "source"; sourceId: string; seriesId: string };

/**
 * The series page — cover, metadata and the chapter list — for that chapter.
 *
 * Source ids and connector series ids are opaque strings that routinely contain
 * slashes, so both segments are percent-encoded; the same contract the source
 * reader and series-detail links already follow.
 */
export function seriesPageHref(series: ChapterSeries): string {
  if (series.scope === "source") {
    return `/sources/${encodeURIComponent(series.sourceId)}/series/${encodeURIComponent(series.seriesId)}`;
  }

  // A malformed reader URL (/reader/abc/1) renders the invalid-route error card,
  // and its way out must not be /library/NaN — an id that resolves to nothing.
  return Number.isFinite(series.seriesId) && series.seriesId > 0
    ? `/library/${series.seriesId}`
    : "/library";
}
