"use client";

import { useCallback, useEffect, useRef } from "react";
import { useSaveProgress } from "./hooks";
import { chapterIndexOf, type StripChapter, type StripPosition } from "./strip";

const PROGRESS_SAVE_MS = 500;

export interface StripProgressInput {
  sourceId: string;
  seriesKey: string;
  /** The strip's loaded chapters, for the numbers a progress row carries. */
  chapters: readonly StripChapter[];
  /** Fires when the reading line crosses into a different chapter. */
  onChapterChange?: (chapterKey: string) => void;
}

/**
 * Reading position for a strip that spans several chapters (spec R1/R2).
 *
 * Progress is per chapter and always has been — `(source, series, chapter)` with
 * a page inside it — so the only new problem a strip creates is knowing WHICH
 * chapter a page belongs to. The strip answers that on every scroll frame; this
 * turns the answer into writes:
 *
 * - the page is recorded against its own chapter, on both sides of a seam, so
 *   "reading into chapter 12 records chapter 12";
 * - crossing forwards marks the chapter left behind complete, because the
 *   debounced tracker never gets to report a final page once the reading line
 *   has moved on;
 * - nothing ever rewinds: scrolling back to re-read is not a claim to be
 *   earlier in a chapter than the reader got to. The server's furthest-wins
 *   merge would refuse it anyway, but the write would still be pointless and
 *   would rewind the optimistic local state the series page reads back.
 */
export function useStripProgress({
  sourceId,
  seriesKey,
  chapters,
  onChapterChange,
}: StripProgressInput): (position: StripPosition) => void {
  const saveProgress = useSaveProgress();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Furthest page already reported, per chapter — a strip visits several. */
  const furthestSent = useRef<Map<string, number>>(new Map());
  const positionRef = useRef<StripPosition | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const completeChapter = useCallback(
    (chapterKey: string) => {
      const chapter = chapters[chapterIndexOf(chapters, chapterKey)];
      if (!chapter || chapter.pages.length === 0) return;
      if (furthestSent.current.get(chapterKey) === chapter.pages.length) return;
      furthestSent.current.set(chapterKey, chapter.pages.length);
      saveProgress.mutate({
        ref: { sourceId, seriesKey, chapterKey },
        body: {
          chapter_number: chapter.chapterNumber,
          last_page: chapter.pages.length,
          page_count: chapter.pages.length,
          is_completed: true,
        },
      });
    },
    [chapters, saveProgress, seriesKey, sourceId],
  );

  return useCallback(
    (position: StripPosition) => {
      const previous = positionRef.current;
      positionRef.current = position;

      if (previous && previous.chapterKey !== position.chapterKey) {
        if (position.chapterIndex > previous.chapterIndex) {
          completeChapter(previous.chapterKey);
        }
        onChapterChange?.(position.chapterKey);
      }

      const furthest = furthestSent.current.get(position.chapterKey) ?? 0;
      if (position.pageNumber <= furthest) return;
      furthestSent.current.set(position.chapterKey, position.pageNumber);

      const chapterNumber =
        chapters[chapterIndexOf(chapters, position.chapterKey)]?.chapterNumber ?? null;
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        saveProgress.mutate({
          ref: { sourceId, seriesKey, chapterKey: position.chapterKey },
          body: {
            chapter_number: chapterNumber,
            last_page: position.pageNumber,
            page_count: position.pageCount,
            is_completed:
              position.pageCount > 0 && position.pageNumber >= position.pageCount,
          },
        });
      }, PROGRESS_SAVE_MS);
    },
    [chapters, completeChapter, onChapterChange, saveProgress, seriesKey, sourceId],
  );
}
