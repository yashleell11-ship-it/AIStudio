import { readScopedString, writeScopedString } from "@/lib/scoped-storage";

/**
 * Where you were in a chapter, per (user, profile).
 *
 * Was device-global: two profiles on one browser that opened the same chapter
 * shared a scroll position, so one persona's place silently moved another's --
 * and it disclosed that they had read it at all. Same leak already closed for
 * source progress, recent searches and reader preferences; this file was skipped
 * at the time only because another agent held the reader directory.
 *
 * With no active profile there is no store rather than a shared one, so a
 * position written before sign-in is never inherited by whoever signs in.
 */
const SCROLL_PREFIX = "manhwamaniacs-reader-scroll:";

function storageKey(chapterKey: string | number): string {
  return `${SCROLL_PREFIX}${chapterKey}`;
}

export function readScrollPosition(chapterKey: string | number): number | null {
  const raw = readScopedString(storageKey(chapterKey));
  if (raw == null) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function writeScrollPosition(chapterKey: string | number, scrollTop: number): void {
  writeScopedString(storageKey(chapterKey), String(Math.round(scrollTop)));
}
