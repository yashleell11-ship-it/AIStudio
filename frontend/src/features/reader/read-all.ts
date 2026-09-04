/**
 * Read-all: the whole series as one continuous scroll (spec 2026-09-05 R2).
 *
 * Everything here is the arithmetic of "which chapters come next", kept apart
 * from the fetching so it can be tested without a network. The strip itself is
 * the same one the plain reader uses — Read-all differs only in where its
 * chapters come from: an ordered series list and the bulk manifest endpoint,
 * rather than one chapter's `prev`/`next` links.
 */

import type { SourceChapterSummary } from "@/features/sources/types";

/** One chapter of a series, in reading order. */
export interface OrderedChapter {
  chapterKey: string;
  number: number | null;
  title: string;
}

/**
 * The series in reading order: chapter 1 first.
 *
 * Derived here rather than trusted from the connector. Most connectors sort
 * ascending, but a few (baozimh, comicland) list newest-first, which makes the
 * manifest's own `next` point at an OLDER chapter — fine for a reader stepping
 * between two chapters, wrong for a run through the whole series. Sorting by
 * number is the one ordering that means the same thing everywhere.
 *
 * Unnumbered chapters keep their source order and sink to the end: they are
 * usually extras and specials, and guessing a position for them would put an
 * omake in the middle of the story.
 */
export function readingOrder(
  chapters: readonly SourceChapterSummary[],
): OrderedChapter[] {
  return chapters
    .map((chapter, index) => ({ chapter, index }))
    .sort((left, right) => {
      const a = left.chapter.number;
      const b = right.chapter.number;
      if (a == null && b == null) return left.index - right.index;
      if (a == null) return 1;
      if (b == null) return -1;
      if (a === b) return left.index - right.index;
      return a - b;
    })
    .map(({ chapter }) => ({
      chapterKey: chapter.id,
      number: chapter.number,
      title: chapter.title,
    }));
}

export function orderIndexOf(
  order: readonly OrderedChapter[],
  chapterKey: string,
): number {
  return order.findIndex((entry) => entry.chapterKey === chapterKey);
}

/**
 * The next window of keys after `lastKey`.
 *
 * `count` is what the strip needs on screen; `stride` is what is actually
 * asked for, because a bulk window costs one round trip whether it carries one
 * chapter or six, and the endpoint is rate-limited per CALL (six a minute — one
 * call is worth up to twenty upstream scrapes). Fetching a chapter at a time
 * would spend that budget in six chapters; a stride spends it in thirty-six.
 */
export function windowAfter(
  order: readonly OrderedChapter[],
  lastKey: string | undefined,
  count: number,
  stride: number,
  cap: number,
): string[] {
  if (order.length === 0 || count <= 0) return [];
  const from = lastKey === undefined ? 0 : orderIndexOf(order, lastKey) + 1;
  if (from <= 0 && lastKey !== undefined) return [];
  const size = Math.max(1, Math.min(Math.max(count, stride), cap));
  return order.slice(from, from + size).map((entry) => entry.chapterKey);
}

/** The chapter immediately before `firstKey`, or null at the start of the series. */
export function keyBefore(
  order: readonly OrderedChapter[],
  firstKey: string | undefined,
): string | null {
  if (firstKey === undefined) return null;
  const index = orderIndexOf(order, firstKey);
  return index > 0 ? order[index - 1].chapterKey : null;
}

/** How a chapter is named at the edge of the strip: its number, else its title. */
export function orderedLabel(
  order: readonly OrderedChapter[],
  chapterKey: string | null,
): string | null {
  if (!chapterKey) return null;
  const entry = order[orderIndexOf(order, chapterKey)];
  if (!entry) return null;
  if (entry.number != null) return `Ch ${entry.number}`;
  return entry.title?.trim() || null;
}

/**
 * Where a Read-all run starts.
 *
 * The furthest chapter with saved progress, if there is one — a reader who has
 * seen forty chapters does not want the run to begin at chapter one — and
 * otherwise the first chapter of the series. Everything before the entry point
 * is still reachable: the strip pulls chapters onto its head when the reader
 * scrolls up past it.
 */
export function readAllEntryKey(
  order: readonly OrderedChapter[],
  resumeKey: string | null,
): string | null {
  if (resumeKey && orderIndexOf(order, resumeKey) >= 0) return resumeKey;
  return order[0]?.chapterKey ?? null;
}
