import { isFullySaved } from "./format";
import { chapterCacheKey } from "./save-request";
import type { SavedChapterEntry } from "./types";

/**
 * What a series page needs to know about what is already on the device.
 *
 * Until now the only place the web said anything about a saved chapter was the
 * reader's own control and the `/downloads` screen, so the answer to "have I
 * got this one?" was "open it and look". These derive that answer for a whole
 * chapter list from the worker's index, which is the same index `/downloads`
 * renders — one source of truth, so the two can never disagree about a chapter.
 */

export type ChapterDownloadState =
  /** Nothing on the device. */
  | "none"
  /** Picked for a run that has not reached it yet. Page-side, not the worker's. */
  | "queued"
  | "saving"
  /** Every page present, nothing outstanding. */
  | "saved"
  /** Interrupted, or pages failed — readable, with holes. */
  | "incomplete"
  /** Stopped for room, not for an error. */
  | "paused"
  /** The source moved the pages underneath it. */
  | "stale";

/** The saved chapters belonging to one series, by chapter key. */
export function savedChaptersForSeries(
  entries: readonly SavedChapterEntry[],
  ref: { sourceId: string; seriesKey: string },
): Map<string, SavedChapterEntry> {
  const found = new Map<string, SavedChapterEntry>();
  for (const entry of entries) {
    if (entry.sourceId !== ref.sourceId || entry.seriesKey !== ref.seriesKey) continue;
    found.set(entry.chapterKey, entry);
  }
  return found;
}

/**
 * One chapter's state, in the same precedence `describeEntry` uses on the
 * `/downloads` screen. Sharing the order matters more than sharing the code:
 * a chapter that reads "Saved" on the series page and "Paused — device is full"
 * two taps away is a bug the reader discovers on a train.
 */
export function chapterDownloadState(
  entry: SavedChapterEntry | null | undefined,
): ChapterDownloadState {
  if (!entry) return "none";
  if (entry.status === "saving") return "saving";
  if (entry.status === "paused") return "paused";
  if (entry.stale) return "stale";
  if (entry.status === "partial" || entry.savedPages < entry.pageCount) {
    return "incomplete";
  }
  return "saved";
}

/**
 * Whether downloading this chapter would do anything.
 *
 * Anything short of complete is worth re-running: the worker skips what is
 * already in the cache, so resuming a half-saved chapter costs only its gaps.
 */
export function needsDownload(entry: SavedChapterEntry | null | undefined): boolean {
  return !isFullySaved(entry);
}

/** How many of `chapters` are fully on the device. */
export function savedCount(
  chapters: readonly { key: string }[],
  saved: ReadonlyMap<string, SavedChapterEntry>,
): number {
  let total = 0;
  for (const chapter of chapters) {
    if (isFullySaved(saved.get(chapter.key))) total += 1;
  }
  return total;
}

/** The cache key for a chapter of this series — what the worker indexes by. */
export function seriesChapterKey(
  ref: { sourceId: string; seriesKey: string },
  chapterKey: string,
): string {
  return chapterCacheKey({ ...ref, chapterKey });
}
