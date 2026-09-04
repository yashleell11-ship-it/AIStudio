/**
 * The continuous strip: several chapters, one scroll.
 *
 * The reader used to render exactly one chapter's pages and swap the whole
 * thing at the boundary. The spec (2026-09-05 R1) asks for the opposite: the
 * last page of chapter N and the first of N+1 in the same scroll, with the seam
 * marked and never blocking. R2 asks for the same thing at series scale.
 *
 * Both are the same object — an ordered list of loaded chapters flattened into
 * one row list — so this module is the single model behind them. It is pure on
 * purpose: the component's only jobs are to measure and to scroll, and every
 * decision it makes about *what* to render is a function tested here.
 *
 * Rows, not pages, because a strip carries three kinds of thing:
 *
 * - `page` — one image, numbered within ITS OWN chapter (progress is per
 *   chapter, so a global page index would be the wrong number to record).
 * - `divider` — the quiet marker naming the chapter being entered.
 * - `spacer` — a chapter whose pages have been released, standing in at exactly
 *   the height they occupied. Releasing this way is what keeps a 300-chapter
 *   Read-all session bounded without ever moving the scroll position: the strip
 *   is the same height before and after, so nothing under the reader shifts.
 */

import type { ReaderChapterContent, ReaderPage } from "./types";

/** A chapter loaded into a strip. Identical to what the reader already builds. */
export type StripChapter = ReaderChapterContent;

export interface StripPageRow {
  kind: "page";
  /** Globally unique (`chapterKey:number`) — stable across array shifts. */
  key: string;
  chapterKey: string;
  chapterIndex: number;
  /** 1-based within its OWN chapter. */
  pageNumber: number;
  pageCount: number;
  /** Its chapter's label, so a page's alt text names the chapter it is in. */
  label: string;
  page: ReaderPage;
}

export interface StripDividerRow {
  kind: "divider";
  key: string;
  /** The chapter being ENTERED — a divider announces what comes next. */
  chapterKey: string;
  chapterIndex: number;
  label: string;
  pageCount: number;
}

export interface StripSpacerRow {
  kind: "spacer";
  key: string;
  chapterKey: string;
  chapterIndex: number;
  pageCount: number;
  /** The exact height the released pages occupied. */
  height: number;
}

export type StripRow = StripPageRow | StripDividerRow | StripSpacerRow;

export interface BuildStripOptions {
  /** Chapters whose pages are released; each becomes one spacer row. */
  released?: ReadonlySet<string>;
  /** Height of a released chapter's spacer, in px. */
  releasedHeight?: (chapterKey: string) => number;
}

/** The label a divider carries. The manifest's title is already "Chapter N". */
export function stripChapterLabel(chapter: StripChapter): string {
  return chapter.title?.trim() || "Chapter";
}

export function stripPageRowKey(chapterKey: string, pageNumber: number): string {
  return `${chapterKey}:${pageNumber}`;
}

/**
 * Flatten loaded chapters into the row list the virtualizer renders.
 *
 * The first chapter gets no divider: the strip opens on the chapter the reader
 * asked for, and a banner above the first page is furniture, not information.
 * Every chapter after it gets one — including, after a prepend, the chapter
 * that used to be first, which is exactly the seam marker that case needs.
 */
export function buildStripRows(
  chapters: readonly StripChapter[],
  options: BuildStripOptions = {},
): StripRow[] {
  const released = options.released;
  const heightOf = options.releasedHeight;
  const rows: StripRow[] = [];

  chapters.forEach((chapter, chapterIndex) => {
    const pageCount = chapter.pages.length;
    const label = stripChapterLabel(chapter);
    if (chapterIndex > 0) {
      rows.push({
        kind: "divider",
        key: `divider:${chapter.chapterKey}`,
        chapterKey: chapter.chapterKey,
        chapterIndex,
        label,
        pageCount,
      });
    }

    if (released?.has(chapter.chapterKey)) {
      rows.push({
        kind: "spacer",
        key: `spacer:${chapter.chapterKey}`,
        chapterKey: chapter.chapterKey,
        chapterIndex,
        pageCount,
        height: Math.max(0, heightOf?.(chapter.chapterKey) ?? 0),
      });
      return;
    }

    chapter.pages.forEach((page, pageIndex) => {
      rows.push({
        kind: "page",
        key: stripPageRowKey(chapter.chapterKey, pageIndex + 1),
        chapterKey: chapter.chapterKey,
        chapterIndex,
        pageNumber: pageIndex + 1,
        pageCount,
        label,
        page,
      });
    });
  });

  return rows;
}

/**
 * Where the reader is, in the terms progress is recorded in.
 *
 * Deliberately a chapter KEY and not an index into the strip: the strip grows
 * at both ends, and a report built one frame ago must still mean the same
 * chapter when it is acted on. Whoever needs a position in the strip looks the
 * key up in the list they hold right now.
 */
export interface StripPosition {
  chapterKey: string;
  /** 1-based page within that chapter. */
  pageNumber: number;
  pageCount: number;
}

/**
 * The position a row reports.
 *
 * A divider reports page 1 of the chapter it introduces, not the last page of
 * the one above: the row that owns the reading line is the announcement of the
 * next chapter, and by the time it has crossed that line the new chapter's
 * first page fills the viewport under it. "Reading into chapter 12 records
 * chapter 12" (spec R2) is this rule.
 */
export function stripPositionAt(
  rows: readonly StripRow[],
  rowIndex: number,
): StripPosition | null {
  const row = rows[rowIndex];
  if (!row) return null;
  return {
    chapterKey: row.chapterKey,
    pageNumber: row.kind === "page" ? row.pageNumber : 1,
    pageCount: row.pageCount,
  };
}

/** Index of a chapter's first PAGE row, or -1 when it has none rendered. */
export function chapterFirstPageRow(
  rows: readonly StripRow[],
  chapterKey: string,
): number {
  return rows.findIndex((row) => row.kind === "page" && row.chapterKey === chapterKey);
}

/** Index of the last row belonging to a chapter, or -1. */
export function chapterLastRow(
  rows: readonly StripRow[],
  chapterKey: string,
): number {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    if (rows[index].chapterKey === chapterKey) return index;
  }
  return -1;
}

/**
 * The row to scroll to for a chapter/page. Falls back to the chapter's first
 * rendered row when the page is out of range (a released chapter has none of
 * its pages rendered, so its spacer answers instead).
 */
export function findStripRow(
  rows: readonly StripRow[],
  chapterKey: string,
  pageNumber: number,
): number {
  let fallback = -1;
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row.chapterKey !== chapterKey) continue;
    if (fallback < 0) fallback = index;
    if (row.kind === "page" && row.pageNumber === pageNumber) return index;
  }
  return fallback;
}

export function chapterIndexOf(
  chapters: readonly StripChapter[],
  chapterKey: string,
): number {
  return chapters.findIndex((chapter) => chapter.chapterKey === chapterKey);
}

/**
 * How many chapters either side of the one being read stay loaded, and how many
 * stay rendered.
 *
 * `ahead: 1` is what makes the seam seamless — the next chapter is pulled the
 * moment the current one becomes active, long before the reader gets near the
 * bottom, so crossing is a scroll and never a wait. It costs one manifest per
 * chapter opened, which the reader already spent on `prefetchChapterManifest`.
 */
export interface StripWindow {
  behind: number;
  ahead: number;
}

/** The plain reader: the chapter you are in, plus its two neighbours. */
export const READER_STRIP_WINDOW: StripWindow = { behind: 1, ahead: 1 };

/**
 * Read-all: one more ahead, because a bulk window costs the same round trip
 * whether it carries one chapter or three, and the reader is committed to
 * going forwards.
 */
export const READ_ALL_STRIP_WINDOW: StripWindow = { behind: 1, ahead: 3 };

/**
 * Chapters rendered as real pages; everything else is released to a spacer.
 *
 * Two either side rather than one: at a seam the viewport can hold the end of
 * one chapter and the start of the next, and a source that publishes one-page
 * chapters can put three or four on screen at once. Releasing something the
 * reader can see would be a hole in the page, so the radius is deliberately
 * wider than the window that loads.
 */
export const RENDER_CHAPTER_RADIUS = 2;

/** Whether the strip should pull another chapter onto its end. */
export function shouldExtendAhead(
  activeIndex: number,
  loadedCount: number,
  ahead: number,
): boolean {
  if (activeIndex < 0 || loadedCount <= 0) return false;
  return activeIndex + ahead > loadedCount - 1;
}

/**
 * Chapters whose pages should be released, given where the reader is.
 *
 * Released, not dropped: the chapter stays in the strip at exactly its old
 * height (see the module note), so this never moves the scroll position and
 * scrolling back into it restores the pages with nothing having shifted.
 */
export function releasedChapterKeys(
  chapters: readonly StripChapter[],
  activeIndex: number,
  radius: number = RENDER_CHAPTER_RADIUS,
): Set<string> {
  const released = new Set<string>();
  if (activeIndex < 0) return released;
  chapters.forEach((chapter, index) => {
    if (Math.abs(index - activeIndex) > radius) {
      released.add(chapter.chapterKey);
    }
  });
  return released;
}

/**
 * The label for the chapter on the other side of a boundary.
 *
 * The manifest carries the neighbour's KEY but not its number, so the label is
 * inferred from this chapter's own — and only when that number is a whole one.
 * Decimal and split chapters (41.5, 41.2) make "Ch 42" a guess that is wrong
 * often enough to be worse than saying nothing, so those just say "chapter".
 */
export function nextChapterLabelFor(
  chapter: StripChapter,
  direction: "next" | "previous" = "next",
): string | null {
  const key =
    direction === "next" ? chapter.nextChapterKey : chapter.previousChapterKey;
  if (!key) return null;
  const number = chapter.chapterNumber;
  if (number == null || !Number.isInteger(number)) {
    return direction === "next" ? "Next chapter" : "Previous chapter";
  }
  return `Ch ${direction === "next" ? number + 1 : number - 1}`;
}

/** What a released chapter leaves behind: one height, and the rows it came from. */
export interface FrozenChapterHeight {
  /** The spacer's height — exactly what the released pages occupied. */
  total: number;
  /** Row key → height, to be remembered so expanding restores the same total. */
  frozen: Array<[string, number]>;
}

/**
 * Fix a chapter's height before its pages are released.
 *
 * The whole releasing scheme rests on one equality: the spacer that replaces a
 * chapter's pages is exactly as tall as they were, so releasing and expanding
 * move nothing. That only holds if the individual heights are FROZEN at the
 * moment of release — a page never measured would otherwise be re-estimated on
 * expansion from a running average that has moved on since, and the chapter
 * would come back a different height than it left.
 *
 * So every row gets a number here, measured where there is one and estimated
 * where there is not, and the caller remembers all of them.
 */
export function freezeChapterHeight(
  chapter: StripChapter,
  measured: ReadonlyMap<string, number>,
  estimate: (page: ReaderPage) => number,
): FrozenChapterHeight {
  const frozen: Array<[string, number]> = [];
  let total = 0;
  chapter.pages.forEach((page, index) => {
    const key = stripPageRowKey(chapter.chapterKey, index + 1);
    const height = measured.get(key) ?? Math.max(0, estimate(page));
    frozen.push([key, height]);
    total += height;
  });
  return { total, frozen };
}
