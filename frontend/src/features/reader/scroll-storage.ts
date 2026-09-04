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
 *
 * A position is a PAGE and an offset inside it, not a raw scroll offset. It was
 * raw pixels while the reader rendered exactly one chapter, where the worst a
 * drifted estimate could do was land you on the wrong page of the right
 * chapter. The strip put several chapters in one scroll (spec 2026-09-05 R1),
 * and the same drift then lands you in the wrong CHAPTER — so the number is
 * anchored to a page, which the strip can find exactly however its estimates
 * have moved. Values written by the old format still read: a bare number is a
 * distance from the chapter's first page, which is what it always meant.
 */
const SCROLL_PREFIX = "manhwamaniacs-reader-scroll:";

export interface ReaderPosition {
  /** 1-based page within the chapter. */
  page: number;
  /** Pixels scrolled past the top of that page. */
  offset: number;
}

function storageKey(chapterKey: string | number): string {
  return `${SCROLL_PREFIX}${chapterKey}`;
}

export function readReaderPosition(chapterKey: string | number): ReaderPosition | null {
  const raw = readScopedString(storageKey(chapterKey));
  if (raw == null) return null;

  const match = /^p:(\d+):(\d+)$/.exec(raw);
  if (match) {
    return { page: Math.max(1, Number(match[1])), offset: Number(match[2]) };
  }

  // Legacy: a bare pixel offset from the start of the chapter.
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return null;
  return { page: 1, offset: Math.round(value) };
}

export function writeReaderPosition(
  chapterKey: string | number,
  position: ReaderPosition,
): void {
  const page = Math.max(1, Math.round(position.page));
  const offset = Math.max(0, Math.round(position.offset));
  writeScopedString(storageKey(chapterKey), `p:${page}:${offset}`);
}
