"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ChapterId } from "@/types/api";
import { ensureChapterPages, useAddBookmark, useSaveProgress } from "../hooks";
import { readerChapterHref, seriesPageHref } from "../reader-link";
import { readerSeriesKey } from "../preferences";
import { chapterIndexOf, READER_STRIP_WINDOW, type StripPosition } from "../strip";
import { linkedChapterSource } from "../strip-source";
import { useChapterStrip } from "../use-chapter-strip";
import { ChapterReader } from "./ChapterReader";

interface SourceReaderProps {
  sourceId: string;
  seriesKey: string;
  chapterKey: string;
  initialPage?: number;
}

const PROGRESS_SAVE_MS = 500;

/**
 * The unified source-native reader (spec §3.3). Every chapter streams from the
 * source page proxy; the service worker transparently answers the same URLs
 * from Cache Storage when the chapter is downloaded.
 *
 * Seamless chapter boundary (spec 2026-09-05 R1): the reader is not one chapter
 * any more, it is a STRIP. The chapter after the one being read is pulled onto
 * it the moment that chapter becomes active, so the last page of N and the
 * first of N+1 sit in the same scroll and the boundary is crossed — in either
 * direction — by scrolling past it. Nothing remounts and no route changes; the
 * URL is corrected with `history.replaceState` as the reader crosses, so a
 * refresh or a shared link still lands on the chapter actually being read.
 *
 * This owns the identity and the writes; `ChapterReader` owns the page and
 * `ContinuousStrip` owns the scroll.
 */
export function SourceReader({
  sourceId,
  seriesKey,
  chapterKey,
  initialPage = 1,
}: SourceReaderProps) {
  const queryClient = useQueryClient();

  // The chapter actually being read. Starts at the routed key; crossing a seam
  // moves it with no navigation at all.
  const [activeChapterKey, setActiveChapterKey] = useState(chapterKey);

  // A real navigation (route change, refresh, deep link) normally remounts via
  // the page's `key`, but follow the props during render anyway if they change
  // under us — the accepted "reset state on prop change" pattern.
  const [routed, setRouted] = useState({ chapterKey, initialPage });
  if (routed.chapterKey !== chapterKey || routed.initialPage !== initialPage) {
    setRouted({ chapterKey, initialPage });
    setActiveChapterKey(chapterKey);
  }

  const source = useMemo(
    () => linkedChapterSource(queryClient, sourceId, seriesKey),
    [queryClient, seriesKey, sourceId],
  );
  const strip = useChapterStrip({
    entryChapterKey: chapterKey,
    activeChapterKey,
    source,
    window: READER_STRIP_WINDOW,
  });

  const saveProgress = useSaveProgress();
  const addBookmark = useAddBookmark();

  const progressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Furthest page already reported, per chapter — a strip visits several. */
  const furthestSent = useRef<Map<string, number>>(new Map());
  const positionRef = useRef<StripPosition | null>(null);

  const chapters = strip.chapters;
  const activeChapter = chapters[chapterIndexOf(chapters, activeChapterKey)];

  const preloadNextChapter = useCallback(async () => {
    const nextKey = activeChapter?.nextChapterKey;
    if (!nextKey) return [];
    return ensureChapterPages(queryClient, {
      sourceId,
      seriesKey,
      chapterKey: nextKey,
    });
  }, [activeChapter?.nextChapterKey, queryClient, seriesKey, sourceId]);

  const pushProgress = useCallback(
    (position: StripPosition, chapterNumber: number | null) => {
      const ref: ChapterId = {
        sourceId,
        seriesKey,
        chapterKey: position.chapterKey,
      };
      saveProgress.mutate({
        ref,
        body: {
          chapter_number: chapterNumber,
          last_page: position.pageNumber,
          page_count: position.pageCount,
          is_completed:
            position.pageCount > 0 && position.pageNumber >= position.pageCount,
        },
      });
    },
    [saveProgress, seriesKey, sourceId],
  );

  /**
   * Mark a chapter the reader has scrolled clear of as finished.
   *
   * The debounced tracker never reports a chapter's final page: by the time the
   * strip settles, the reading line is already in the next chapter. Without
   * this, every chapter read in one continuous sitting would be left one page
   * short of complete.
   */
  const completeChapter = useCallback(
    (chapterKey_: string) => {
      const chapter = chapters[chapterIndexOf(chapters, chapterKey_)];
      if (!chapter || chapter.pages.length === 0) return;
      if (furthestSent.current.get(chapterKey_) === chapter.pages.length) return;
      furthestSent.current.set(chapterKey_, chapter.pages.length);
      saveProgress.mutate({
        ref: { sourceId, seriesKey, chapterKey: chapterKey_ },
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

  /**
   * Everything that follows the reader across a seam.
   *
   * Progress is attributed to the chapter the page belongs to, on both sides of
   * the boundary (spec R1), and never rewound: scrolling back to re-read is not
   * a claim that the reader is earlier in the chapter than they got to.
   */
  const handlePosition = useCallback(
    (position: StripPosition) => {
      const previous = positionRef.current;
      positionRef.current = position;

      if (previous && previous.chapterKey !== position.chapterKey) {
        if (position.chapterIndex > previous.chapterIndex) {
          completeChapter(previous.chapterKey);
        }
        setActiveChapterKey(position.chapterKey);
        window.history.replaceState(
          window.history.state,
          "",
          readerChapterHref({ sourceId, seriesKey, chapterKey: position.chapterKey }),
        );
      }

      const furthest = furthestSent.current.get(position.chapterKey) ?? 0;
      if (position.pageNumber <= furthest) return;
      furthestSent.current.set(position.chapterKey, position.pageNumber);

      const chapterNumber =
        chapters[chapterIndexOf(chapters, position.chapterKey)]?.chapterNumber ?? null;
      if (progressTimer.current) clearTimeout(progressTimer.current);
      progressTimer.current = setTimeout(
        () => pushProgress(position, chapterNumber),
        PROGRESS_SAVE_MS,
      );
    },
    [chapters, completeChapter, pushProgress, seriesKey, sourceId],
  );

  const handleBookmark = useCallback(
    (page: number) => {
      addBookmark.mutate({
        ref: { sourceId, seriesKey, chapterKey: activeChapterKey },
        page,
      });
    },
    [activeChapterKey, addBookmark, seriesKey, sourceId],
  );

  useEffect(() => {
    return () => {
      if (progressTimer.current) clearTimeout(progressTimer.current);
    };
  }, []);

  return (
    <ChapterReader
      chapters={chapters}
      entryChapterKey={chapterKey}
      isLoading={strip.isLoading}
      error={strip.error}
      onRetry={strip.reload}
      seriesKey={readerSeriesKey(sourceId, seriesKey)}
      initialPage={routed.initialPage}
      seriesHref={seriesPageHref({ sourceId, seriesKey })}
      onPosition={handlePosition}
      onBookmark={handleBookmark}
      onLoadPrevious={strip.loadPrevious}
      loadingPrevious={strip.loadingPrevious}
      nextError={strip.nextError}
      onRetryNext={strip.retryNext}
      preloadNextChapter={preloadNextChapter}
      bookmarkPending={addBookmark.isPending}
      showBookmark
    />
  );
}
