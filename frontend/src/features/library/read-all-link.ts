/**
 * "Read all" on the library's own series page (spec 2026-09-05 R2).
 *
 * The decision lives here rather than inline in `SeriesDetailView` for the
 * reason every other library rule does (`url-state`, `continue-reading`,
 * `bulk`): the vitest gate runs in node and cannot render a component, so a
 * rule that matters gets its own module and its own test.
 */

import { readAllHref } from "@/features/reader/reader-link";
import type { SeriesId } from "@/types/api";

/**
 * Where "Read all" goes from the library series page, or null when the page
 * must not offer it.
 *
 * Two of the three conditions are the source series page's, copied so the two
 * pages agree about when the button exists: there is nothing to read THROUGH
 * in a single-chapter series, and the run starts where the reader left off
 * rather than at chapter one.
 *
 * The third is this page's alone. The library shelves novels beside manga and
 * the command palette links every library hit straight here, so a novel CAN
 * reach this page — and Read-all is the page strip, which prose has no pages
 * for. `undefined` (the sources listing has not answered yet) holds the button
 * back instead of guessing: guessing wrong offers a novel a reader that cannot
 * open it, and a button that appears a frame late costs nothing.
 */
export function libraryReadAllHref(
  ref: SeriesId,
  chapterCount: number,
  resumeChapterKey: string | null,
  isNovel: boolean | undefined,
): string | null {
  if (isNovel !== false) return null;
  if (chapterCount < 2) return null;
  return readAllHref(ref, resumeChapterKey);
}
