import { resolveViewState } from "@/lib/view-state";

/**
 * What the chapter list on a source's series page should be showing.
 *
 * Built on `resolveViewState` (loading | offline | error | empty | content) with
 * one extra case the shared resolver cannot know about: a source can answer
 * successfully with ZERO chapters for a series whose own summary says it has
 * hundreds. That is a connector failure wearing an empty response, and it used
 * to render as the same "No chapters available." as a genuinely empty series —
 * with no way to tell that retrying was worth doing.
 */
export type ChapterListState =
  | "loading"
  | "offline"
  | "error"
  /** The source claims chapters exist but returned none. Retry is worth it. */
  | "unavailable"
  /** The source genuinely has no chapters for this series. */
  | "empty"
  | "content";

export interface ChapterListStateInput {
  isLoading: boolean;
  error: unknown;
  /** How many chapters the chapters request actually returned. */
  chapterCount: number;
  /** How many the series summary says the source has. */
  reportedChapterCount: number;
}

export function resolveChapterListState({
  isLoading,
  error,
  chapterCount,
  reportedChapterCount,
}: ChapterListStateInput): ChapterListState {
  const base = resolveViewState({
    isLoading,
    error,
    isEmpty: chapterCount === 0,
  });
  if (base !== "empty") return base;
  return reportedChapterCount > 0 ? "unavailable" : "empty";
}
