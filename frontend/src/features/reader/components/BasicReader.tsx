"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ensureReaderChapterPages,
  useAddBookmark,
  useAdjacentChapter,
  useReaderChapter,
  useSaveProgress,
} from "../hooks";
import { toReaderChapterContent } from "../api";
import { readerDebug } from "../debug";
import { readerSeriesKey } from "../preferences";
import { ApiError } from "@/types/api";
import { ChapterReader } from "./ChapterReader";

interface BasicReaderProps {
  seriesId: number;
  chapterId: number;
  initialPage?: number;
}

export function BasicReader({ seriesId, chapterId, initialPage = 1 }: BasicReaderProps) {
  const invalidRoute =
    !Number.isFinite(seriesId) ||
    seriesId <= 0 ||
    !Number.isFinite(chapterId) ||
    chapterId <= 0;
  const resolvedChapterId = invalidRoute ? 0 : chapterId;
  const queryClient = useQueryClient();
  const chapterQuery = useReaderChapter(resolvedChapterId);
  const saveProgress = useSaveProgress();
  const addBookmark = useAddBookmark();
  const previousChapter = useAdjacentChapter(chapterId, "previous");
  const nextChapter = useAdjacentChapter(chapterId, "next");
  const lastSavedPage = useRef(0);
  const pendingPageRef = useRef<number | null>(null);
  const persistProgressRef = useRef<(page: number) => void>(() => {});

  useEffect(() => {
    readerDebug("route-entered", {
      scope: "local",
      seriesId,
      chapterId,
      initialPage,
    });
  }, [seriesId, chapterId, initialPage]);

  useEffect(() => {
    if (!chapterQuery.data) return;
    readerDebug("reader-response", {
      scope: "local",
      chapterId,
      pageCount: chapterQuery.data.page_count,
      pagesLength: chapterQuery.data.pages?.length ?? 0,
      status: chapterQuery.status,
      fetchStatus: chapterQuery.fetchStatus,
    });
  }, [chapterId, chapterQuery.data, chapterQuery.fetchStatus, chapterQuery.status]);

  const chapter = useMemo(
    () => (chapterQuery.data ? toReaderChapterContent(chapterQuery.data) : undefined),
    [chapterQuery.data],
  );

  const previousChapterHref =
    previousChapter.data?.id != null
      ? `/reader/${seriesId}/${previousChapter.data.id}`
      : null;
  const nextChapterHref =
    nextChapter.data?.id != null ? `/reader/${seriesId}/${nextChapter.data.id}` : null;

  const nextChapterId = nextChapter.data?.id ?? null;
  const preloadNextChapter = useCallback(
    () =>
      nextChapterId != null
        ? ensureReaderChapterPages(queryClient, nextChapterId)
        : Promise.resolve([]),
    [nextChapterId, queryClient],
  );

  const persistProgress = useCallback(
    (page: number) => {
      if (page <= 0 || page === lastSavedPage.current) return;
      lastSavedPage.current = page;
      saveProgress.mutate({
        series_id: seriesId,
        chapter_id: chapterId,
        last_page: page,
      });
    },
    [chapterId, saveProgress, seriesId],
  );

  useEffect(() => {
    persistProgressRef.current = persistProgress;
  }, [persistProgress]);

  const handleBookmark = useCallback(
    (page: number) => {
      persistProgress(page);
      addBookmark.mutate({
        series_id: seriesId,
        chapter_id: chapterId,
        page,
      });
    },
    [addBookmark, chapterId, persistProgress, seriesId],
  );

  const progressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current);
        progressTimerRef.current = null;
      }
      const pending = pendingPageRef.current;
      if (pending != null && pending > 0 && pending !== lastSavedPage.current) {
        persistProgressRef.current(pending);
      }
    };
  }, []);

  const handlePageProgress = useCallback(
    (page: number) => {
      pendingPageRef.current = page;
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current);
      }
      progressTimerRef.current = setTimeout(() => {
        persistProgress(page);
      }, 500);
    },
    [persistProgress],
  );

  const routeError = invalidRoute
    ? new ApiError(400, {
        code: "invalid_reader_route",
        message: "This chapter link is invalid.",
      })
    : null;

  return (
    <ChapterReader
      chapter={chapter}
      isLoading={!invalidRoute && chapterQuery.isPending && chapterQuery.data === undefined}
      error={routeError ?? chapterQuery.error}
      scrollKey={String(chapterId)}
      seriesKey={readerSeriesKey(null, seriesId)}
      initialPage={initialPage}
      previousChapterHref={previousChapterHref}
      nextChapterHref={nextChapterHref}
      backHref={`/library/${seriesId}`}
      onBookmark={handleBookmark}
      onPageProgress={handlePageProgress}
      preloadNextChapter={preloadNextChapter}
      bookmarkPending={addBookmark.isPending}
      showBookmark
    />
  );
}
