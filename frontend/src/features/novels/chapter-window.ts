/**
 * The rules for reading a `POST /novels/chapters` answer.
 *
 * The window degrades PER CHAPTER — the server answers each key with a status
 * and exactly one of `chapter`/`error` — so "did the request succeed" is the
 * wrong question to ask of it. One bad chapter in a window of twenty costs
 * that chapter and nothing else, and the caller needs to know which.
 *
 * Pure on purpose: this is the half of the bulk path worth testing, and it is
 * the same rule set the phone applies in `NovelChapterWindow.fromJson`, so the
 * two clients agree about what "the window did not give me chapter 12" means.
 */

import type { NovelChapterPayload, NovelChapterWindowPayload } from "./types";

/**
 * Chapters the client will ask for in a single window.
 *
 * The backend's documented default (`MM_NOVEL_BULK_MAX_CHAPTERS`, 20). A
 * deployment can lower it, and every answer echoes its real value as
 * `max_chapters`, so a caller that has seen one answer should pass that
 * instead — this is only the safe assumption before the first reply lands.
 */
export const NOVEL_WINDOW_CAP = 20;

export interface NovelChapterWindow {
  /** Chapters that arrived with prose, by the key the caller asked for. */
  chapters: ReadonlyMap<string, NovelChapterPayload>;
  /**
   * Per-chapter failures, by the key the caller asked for.
   *
   * Separate from "the window did not mention it" so a caller can tell a
   * broken chapter from a missing one; both fall back to the single-chapter
   * path, which owns the retry.
   */
  failures: ReadonlyMap<string, string>;
}

/** Shown when the server reported a failure with no message of its own. */
const GENERIC_FAILURE = "This chapter could not be fetched.";

/**
 * The keys a window may ask for, clamped to the server's cap.
 *
 * Over the cap is a 413 that fails the WHOLE window, so a caller holding three
 * hundred chapter keys has to stride rather than ask once. Clamping here means
 * no caller has to remember that.
 */
export function boundedWindow(
  chapterKeys: readonly string[],
  cap: number = NOVEL_WINDOW_CAP,
): string[] {
  // A cap that is not a number at all is no report; a cap that IS a number is
  // believed, but only downwards and never below one — a deployment answering
  // 0 must not turn every warm into a silent no-op.
  const reported = Number.isFinite(cap) ? Math.floor(cap) : NOVEL_WINDOW_CAP;
  return chapterKeys.slice(0, Math.max(1, Math.min(reported, NOVEL_WINDOW_CAP)));
}

/**
 * Split a window's answer into the chapters that came back and the ones that
 * did not.
 *
 * Keyed by the REQUESTED spelling, not the echoed one. The server
 * percent-decodes the keys it was given, so a key carrying a literal `%` comes
 * back spelled differently — and the caller's cache, its queue and its chapter
 * list all use the spelling the caller holds. Items arrive in request order,
 * one per key, so position is the reliable pairing; the echoed key is the
 * fallback for any answer that does not line up.
 */
export function collectChapterWindow(
  requested: readonly string[],
  payload: NovelChapterWindowPayload,
): NovelChapterWindow {
  const chapters = new Map<string, NovelChapterPayload>();
  const failures = new Map<string, string>();
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const aligned = items.length === requested.length;

  items.forEach((item, index) => {
    const key = aligned ? requested[index] : item?.chapter_key;
    if (typeof key !== "string" || key === "") return;

    const chapter = item?.status === "ok" ? item.chapter : null;
    if (chapter) {
      // A chapter with no prose is not a chapter. Recording it as a failure
      // keeps it off the cache and on the single-chapter path, where the
      // reader's own "this chapter is empty" handling already lives — caching
      // it would make the emptiness stick for the whole stale window.
      if (Array.isArray(chapter.paragraphs) && chapter.paragraphs.length > 0) {
        chapters.set(key, chapter);
      } else {
        failures.set(key, "This chapter has no text.");
      }
      return;
    }

    failures.set(key, item?.error?.message || GENERIC_FAILURE);
  });

  return { chapters, failures };
}
