/**
 * When the reader pulls the next chapter's payload, and how much of it to warm.
 *
 * Reaching the last page used to dead-end into a cold fetch. Preloading is
 * deliberately shallow: ONE chapter ahead, a handful of images. Chapter payloads
 * for online sources are scraped on demand, so pulling further ahead spends
 * someone else's bandwidth on pages the reader will most likely never show.
 */

/** Hard cap on how far ahead chapter payloads are pulled. */
export const MAX_PRELOAD_CHAPTERS_AHEAD = 1;

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
