"use client";

import { useCallback, useMemo, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ChapterId } from "@/types/api";
import { manifestToChapterContent } from "../api";
import {
  ensureChapterPages,
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
 * TODO(1b): reader viewing-experience polish (seamless pages, cinema mode,
 * seamless chapter transitions, mood tint, continue-hero) is the dedicated
 * later slice — spec §3.3.1–8, step 6.
 */
export function SourceReader({
  sourceId,
  seriesKey,
  chapterKey,
  initialPage = 1,
}: SourceReaderProps) {
  const queryClient = useQueryClient();
  const ref: ChapterId = { sourceId, seriesKey, chapterKey };
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
  const preloadNextChapter = useCallback(async () => {
    if (!nextChapterKey) return [];
    return ensureChapterPages(queryClient, {
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
    [chapter?.chapterNumber, chapterKey, saveProgress, seriesKey, sourceId],
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
    [addBookmark, chapterKey, seriesKey, sourceId],
  );

  return (
    <ChapterReader
      chapter={chapter}
      isLoading={manifestQuery.isPending && manifestQuery.data === undefined}
      error={manifestQuery.error}
      scrollKey={`${sourceId}:${seriesKey}:${chapterKey}`}
      seriesKey={readerSeriesKey(sourceId, seriesKey)}
      initialPage={initialPage}
      previousChapterHref={previousChapterHref}
      nextChapterHref={nextChapterHref}
      seriesHref={seriesPageHref({ sourceId, seriesKey })}
      onBookmark={handleBookmark}
      onPageProgress={handlePageProgress}
      preloadNextChapter={preloadNextChapter}
      bookmarkPending={addBookmark.isPending}
      showBookmark
    />
  );
}
