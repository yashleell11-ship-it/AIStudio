/**
 * When the reader pulls the next chapter's payload, and how much of it to warm.
 *
 * Reaching the last page used to dead-end into a cold fetch. Preloading is
 * deliberately shallow: ONE chapter ahead, a handful of images. Chapter payloads
 * for online sources are scraped on demand, so pulling further ahead spends
 * someone else's bandwidth on pages the reader will most likely never show.
 *
 * SCOPE: the PAGED modes only. Nothing here is on the continuous strip's path,
 * and nothing here is on Read-all's — `useChapterPreload` is armed with
 * `!continuous`, and the strip does its own look-ahead in two places that are
 * better suited to it: `shouldExtendAhead` (strip.ts) pulls the next chapter's
 * manifest when the reader comes within `ahead` CHAPTERS of the loaded tail —
 * counted in chapters, so it behaves identically on a 3,000px chapter and a
 * 40,000px one, which neither a ratio nor a page count does — and
 * `ContinuousStrip`'s own prefetch warms `PRELOAD_AHEAD_CONTINUOUS` page rows
 * across the whole strip, spilling over the seam by construction. Tuning
 * `PRELOAD_TRIGGER_RATIO` or `MAX_PRELOAD_CHAPTERS_AHEAD` will not move a
 * Read-all run one page.
 */

import type { ReadingMode } from "./types";

/** Hard cap on how far ahead chapter payloads are pulled. */
export const MAX_PRELOAD_CHAPTERS_AHEAD = 1;

/**
 * How many upcoming pages of the CURRENT chapter to keep warmed into the browser
 * cache, by reading mode. Continuous scrolling burns through pages fastest and
 * shows partial pages at the seam, so it looks furthest ahead; the paged modes
 * only ever need the next turn or two ready.
 */
export const PRELOAD_AHEAD_CONTINUOUS = 5;
export const PRELOAD_AHEAD_PAGED = 3;

export function pagesAheadToWarm(mode: ReadingMode): number {
  return mode === "continuous" ? PRELOAD_AHEAD_CONTINUOUS : PRELOAD_AHEAD_PAGED;
}

/** Fraction of a chapter that must be read before the next one is pulled. */
export const PRELOAD_TRIGGER_RATIO = 0.6;

/** Always pull once this few pages remain, however long the chapter is. */
export const PRELOAD_TAIL_PAGES = 3;

/** First images of the next chapter to decode ahead of the page turn. */
export const PRELOAD_WARM_IMAGES = 3;

export interface PreloadTriggerInput {
  page: number;
  pageCount: number;
  ratio?: number;
  tail?: number;
}

export function shouldPreloadNextChapter({
  page,
  pageCount,
  ratio = PRELOAD_TRIGGER_RATIO,
  tail = PRELOAD_TAIL_PAGES,
}: PreloadTriggerInput): boolean {
  if (!Number.isFinite(page) || !Number.isFinite(pageCount)) return false;
  if (pageCount <= 0 || page <= 0) return false;
  if (pageCount - page <= tail) return true;
  return page / pageCount >= ratio;
}

/** The leading image URLs of a chapter, de-duplicated, capped at `count`. */
export function warmupImageUrls(
  pages: ReadonlyArray<{ imageUrl: string }>,
  count = PRELOAD_WARM_IMAGES,
): string[] {
  if (count <= 0) return [];
  const urls: string[] = [];
  for (const page of pages) {
    if (urls.length >= count) break;
    if (page.imageUrl && !urls.includes(page.imageUrl)) {
      urls.push(page.imageUrl);
    }
  }
  return urls;
}

export interface ConnectionHint {
  type?: string;
  saveData?: boolean;
}

/**
 * Preloading is optional work, so it yields to the user's data budget — the
 * same rule the download-while-reading queue already applies.
 */
export function connectionAllowsPreload(connection: ConnectionHint | undefined): boolean {
  if (!connection) return true;
  if (connection.saveData === true) return false;
  return connection.type !== "cellular";
}

/**
 * The same rule, asked of the browser this is running in.
 *
 * Every speculative fetch in the app has to make this decision, and each one
 * reading `navigator.connection` for itself is how they drift apart — the
 * series page's open-time chapter warm-up did exactly that, and warmed five
 * chapters over a cellular connection while the reader beside it was politely
 * declining to warm one. Server-side (no `navigator`) it answers `true`, which
 * is inert: nothing preloads there.
 */
export function browserAllowsPreload(): boolean {
  if (typeof navigator === "undefined") return true;
  return connectionAllowsPreload(
    (navigator as Navigator & { connection?: ConnectionHint }).connection,
  );
}
