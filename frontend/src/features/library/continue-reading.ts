import type { ContinueReadingItem } from "./types";

/**
 * Source-native identity helpers for the continue-reading section (spec §3.3.5).
 *
 * Every item is keyed and linked by `(source_id, series_key, chapter_key)` —
 * there is no integer series/chapter id any more. The series title is not in the
 * progress payload, so it is joined from the followed-series index with a
 * graceful fall back to the raw key.
 */

export function continueReadingRef(item: ContinueReadingItem) {
  return {
    sourceId: item.source_id,
    seriesKey: item.series_key,
    chapterKey: item.chapter_key,
  };
}

/** Stable list key for an item. */
export function continueReadingKey(item: ContinueReadingItem): string {
  return `${item.source_id}:${item.series_key}:${item.chapter_key}`;
}

/*
 * There is deliberately no `continueReadingHref` here any more.
 *
 * A resume link has to know which reader its source opens in, and that answer
 * lives in the sources listing — not in a pure helper over one row. The rail
 * builds its links with `useChapterHref` (`features/novels/use-chapter-href`),
 * which is the single place the manga/novel branch is made.
 */

/** Followed-index lookup key for the title join. */
export function continueReadingSeriesKey(item: ContinueReadingItem): string {
  return `${item.source_id}:${item.series_key}`;
}

export function resolveSeriesTitle(
  item: ContinueReadingItem,
  titles: ReadonlyMap<string, string>,
): string {
  return titles.get(continueReadingSeriesKey(item)) ?? item.series_key;
}

/** Percentage of the chapter read, clamped to 0–100. */
export function continueReadingPercent(item: ContinueReadingItem): number {
  return item.page_count > 0
    ? Math.min(100, Math.max(0, Math.round((item.last_page / item.page_count) * 100)))
    : 0;
}

export function continueReadingChapterLabel(item: ContinueReadingItem): string {
  return item.chapter_number != null ? `Ch ${item.chapter_number}` : item.chapter_key;
}
