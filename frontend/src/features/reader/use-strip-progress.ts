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
  /**
   * Furthest page already REPORTED, per chapter — a strip visits several.
   *
   * Reported, not written: a report only arms the debounce below, and the next
   * scroll frame disarms it again. This map exists to stop the reader rewinding
   * within a chapter, and it must never be read as "the server has this".
   */
  const furthestSeen = useRef<Map<string, number>>(new Map());
  /**
   * Chapters whose completion HAS actually been sent.
   *
   * Separate from `furthestSeen` on purpose, and the distinction is the whole
   * point: reading a chapter straight through sets `furthestSeen` to its last
   * page while only arming a 500 ms timer, and crossing the seam clears that
   * timer before it fires. A `completeChapter` that took `furthestSeen` as
   * proof of a write therefore skipped the one write that survives the
   * crossing, and a reader who read four chapters in one scroll had three of
   * them recorded nowhere at all.
   */
  const completedSent = useRef<Set<string>>(new Set());
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
      if (completedSent.current.has(chapterKey)) return;
      completedSent.current.add(chapterKey);
      furthestSeen.current.set(chapterKey, chapter.pages.length);
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
        // Everything the reading line passed OVER is finished, not just the
        // chapter directly above: one wheel gesture can clear a short chapter
        // between two frames, and it would otherwise be left half-read for
        // ever. Resolved against the live strip rather than the reported
        // index, so a report built from an older row list still lands right.
        const from = chapterIndexOf(chapters, previous.chapterKey);
        const to = chapterIndexOf(chapters, position.chapterKey);
        for (let index = from; index >= 0 && index < to; index += 1) {
          completeChapter(chapters[index].chapterKey);
        }
        onChapterChange?.(position.chapterKey);
      }

      const furthest = furthestSeen.current.get(position.chapterKey) ?? 0;
      if (position.pageNumber <= furthest) return;
      furthestSeen.current.set(position.chapterKey, position.pageNumber);

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
