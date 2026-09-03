"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ChapterId } from "@/types/api";
import { manifestToChapterContent } from "../api";
import {
  ensureChapterPages,
  prefetchChapterManifest,
  useAddBookmark,
  useChapterManifest,
  useSaveProgress,
} from "../hooks";
import { readerChapterHref, seriesPageHref } from "../reader-link";
import { readerSeriesKey } from "../preferences";
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
 * Seamless chapter transition (spec §3.3.4): in continuous mode the end of a
 * chapter shows a slide-up end-card for the (already-prefetched) next chapter.
 * Acting on it swaps the chapter content in place — the `ChapterReader` remounts
 * for the new key, but there is no route navigation, so no full-page flash — and
 * the URL is corrected with `history.replaceState`.
 */
export function SourceReader({
  sourceId,
  seriesKey,
  chapterKey,
  initialPage = 1,
}: SourceReaderProps) {
  const queryClient = useQueryClient();

  // The chapter actually on screen. Starts at the routed key; a seamless
  // transition advances it without a navigation.
  const [activeChapterKey, setActiveChapterKey] = useState(chapterKey);
  const [resumePage, setResumePage] = useState(initialPage);

  // A real navigation (route change, refresh, deep link) normally remounts via
  // the page's `key`, but follow the props during render anyway if they change
  // under us — the accepted "reset state on prop change" pattern.
  const [routed, setRouted] = useState({ chapterKey, initialPage });
  if (routed.chapterKey !== chapterKey || routed.initialPage !== initialPage) {
    setRouted({ chapterKey, initialPage });
    setActiveChapterKey(chapterKey);
    setResumePage(initialPage);
  }

  const ref: ChapterId = { sourceId, seriesKey, chapterKey: activeChapterKey };
  const manifestQuery = useChapterManifest(ref);
  const saveProgress = useSaveProgress();
  const addBookmark = useAddBookmark();

  const progressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSavedPage = useRef(0);

  const chapter = useMemo(
    () =>
      manifestQuery.data ? manifestToChapterContent(manifestQuery.data) : undefined,
    [manifestQuery.data],
  );

  const previousChapterHref = chapter?.previousChapterKey
    ? readerChapterHref({ sourceId, seriesKey, chapterKey: chapter.previousChapterKey })
    : null;
  const nextChapterHref = chapter?.nextChapterKey
    ? readerChapterHref({ sourceId, seriesKey, chapterKey: chapter.nextChapterKey })
    : null;

  const nextChapterKey = chapter?.nextChapterKey ?? null;
  // The manifest carries the next chapter's KEY but not its number. Only offer a
  // "Ch N+1" label when this chapter's number is a whole number — decimal /
  // split chapters make the guess unreliable, so those just say "Next chapter".
  const nextChapterLabel = nextChapterKey
    ? chapter?.chapterNumber != null && Number.isInteger(chapter.chapterNumber)
      ? `Ch ${chapter.chapterNumber + 1}`
      : "Next chapter"
    : null;

  const preloadNextChapter = useCallback(async () => {
    if (!nextChapterKey) return [];
    return ensureChapterPages(queryClient, {
      sourceId,
      seriesKey,
      chapterKey: nextChapterKey,
    });
  }, [nextChapterKey, queryClient, seriesKey, sourceId]);

  // Keep the next chapter's manifest warm as soon as this one resolves, so the
  // end-card's "already prefetched" promise holds even for a short chapter the
  // reader scrolls straight through.
  useEffect(() => {
    if (!nextChapterKey) return;
    prefetchChapterManifest(queryClient, {
      sourceId,
      seriesKey,
      chapterKey: nextChapterKey,
    });
  }, [nextChapterKey, queryClient, seriesKey, sourceId]);

  const persistProgress = useCallback(
    (page: number, pageCount: number) => {
      if (page <= 0 || page === lastSavedPage.current) return;
      lastSavedPage.current = page;
      saveProgress.mutate({
        ref,
        body: {
          chapter_number: chapter?.chapterNumber ?? null,
          last_page: page,
          page_count: pageCount,
          is_completed: pageCount > 0 && page >= pageCount,
        },
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chapter?.chapterNumber, activeChapterKey, saveProgress, seriesKey, sourceId],
  );

  const handlePageProgress = useCallback(
    (page: number, pageCount: number) => {
      if (progressTimer.current) clearTimeout(progressTimer.current);
      progressTimer.current = setTimeout(
        () => persistProgress(page, pageCount),
        PROGRESS_SAVE_MS,
      );
    },
    [persistProgress],
  );

  const handleBookmark = useCallback(
    (page: number) => {
      addBookmark.mutate({ ref, page });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [addBookmark, activeChapterKey, seriesKey, sourceId],
  );

  const advanceToNextChapter = useCallback(() => {
    if (!nextChapterKey || !chapter) return;

    // Mark the finished chapter complete straight away — the debounced page
    // tracker never reports the very last page once the strip stops scrolling.
    if (progressTimer.current) {
      clearTimeout(progressTimer.current);
      progressTimer.current = null;
    }
    const finishedRef: ChapterId = { sourceId, seriesKey, chapterKey: activeChapterKey };
    saveProgress.mutate({
      ref: finishedRef,
      body: {
        chapter_number: chapter.chapterNumber,
        last_page: chapter.pageCount,
        page_count: chapter.pageCount,
        is_completed: true,
      },
    });

    void preloadNextChapter();
    lastSavedPage.current = 0;
    setResumePage(1);
    setActiveChapterKey(nextChapterKey);
    const href = readerChapterHref({ sourceId, seriesKey, chapterKey: nextChapterKey });
    window.history.replaceState(window.history.state, "", href);
  }, [
    activeChapterKey,
    chapter,
    nextChapterKey,
    preloadNextChapter,
    saveProgress,
    seriesKey,
    sourceId,
  ]);

  useEffect(() => {
    return () => {
      if (progressTimer.current) clearTimeout(progressTimer.current);
    };
  }, []);

  return (
    <ChapterReader
      key={activeChapterKey}
      chapter={chapter}
      isLoading={manifestQuery.isPending && manifestQuery.data === undefined}
      error={manifestQuery.error}
      scrollKey={`${sourceId}:${seriesKey}:${activeChapterKey}`}
      seriesKey={readerSeriesKey(sourceId, seriesKey)}
      initialPage={resumePage}
      previousChapterHref={previousChapterHref}
      nextChapterHref={nextChapterHref}
      nextChapterLabel={nextChapterLabel}
      onSeamlessNext={nextChapterKey ? advanceToNextChapter : undefined}
      seriesHref={seriesPageHref({ sourceId, seriesKey })}
      onBookmark={handleBookmark}
      onPageProgress={handlePageProgress}
      preloadNextChapter={preloadNextChapter}
      bookmarkPending={addBookmark.isPending}
      showBookmark
    />
  );
}
