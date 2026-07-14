"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toRemoteReaderChapterContent } from "../api";
import { readerDebug } from "../debug";
import { ChapterReader } from "./ChapterReader";
import { useDownloads, useQueueChapters } from "@/features/downloads/hooks";
import { setSourceChapterProgress } from "@/features/sources/source-progress";
import {
  sourceReaderChapterPath,
  useSourceChapters,
  useSourceReaderChapter,
} from "@/features/sources/hooks";

interface SourceReaderProps {
  sourceId: string;
  seriesId: string;
  chapterId: string;
  initialPage?: number;
}

interface NetworkInformation {
  type?: string;
  saveData?: boolean;
}

const ACTIVE_DOWNLOAD_STATES = ["queued", "downloading", "completed"];
const PROGRESS_SAVE_MS = 400;

/** Ascending reading order (lowest chapter number first, unnumbered last). */
function byReadingOrder<T extends { number: number | null }>(a: T, b: T): number {
  if (a.number == null && b.number == null) return 0;
  if (a.number == null) return 1;
  if (b.number == null) return -1;
  return a.number - b.number;
}

export function SourceReader({
  sourceId,
  seriesId,
  chapterId,
  initialPage = 1,
}: SourceReaderProps) {
  const chapterQuery = useSourceReaderChapter(sourceId, seriesId, chapterId);
  const chaptersQuery = useSourceChapters(sourceId, seriesId);
  const downloadsQuery = useDownloads();
  const queueChapters = useQueueChapters();

  const autoQueuedRef = useRef<string | null>(null);
  const progressTimerRef = useRef<number | null>(null);
  const [autoQueueNotice, setAutoQueueNotice] = useState(false);

  useEffect(() => {
    readerDebug("route-entered", {
      scope: "source",
      sourceId,
      seriesId,
      chapterId,
      initialPage,
    });
  }, [sourceId, seriesId, chapterId, initialPage]);

  useEffect(() => {
    if (!chapterQuery.data) return;
    readerDebug("reader-response", {
      scope: "source",
      sourceId,
      chapterId,
      pageCount: chapterQuery.data.page_count,
      pagesLength: chapterQuery.data.pages?.length ?? 0,
      status: chapterQuery.status,
      fetchStatus: chapterQuery.fetchStatus,
    });
  }, [
    chapterId,
    chapterQuery.data,
    chapterQuery.fetchStatus,
    chapterQuery.status,
    sourceId,
  ]);

  // Download-while-reading: best-effort auto-queue of the next two chapters,
  // once per chapter mount, skipping any already queued/downloaded.
  useEffect(() => {
    const chapters = chaptersQuery.data;
    if (!chapters || chapters.length === 0) return;
    if (downloadsQuery.data === undefined) return; // wait so dedup is accurate
    if (autoQueuedRef.current === chapterId) return;

    const connection = (navigator as Navigator & { connection?: NetworkInformation })
      .connection;
    if (connection?.type === "cellular" || connection?.saveData === true) {
      autoQueuedRef.current = chapterId; // respect data-saver; don't retry
      return;
    }

    const ordered = [...chapters].sort(byReadingOrder);
    const index = ordered.findIndex((chapter) => chapter.id === chapterId);
    if (index === -1) return; // current chapter not in list yet; retry when it is
    autoQueuedRef.current = chapterId;

    const nextChapters = ordered.slice(index + 1, index + 3);
    if (nextChapters.length === 0) return;

    const downloads = downloadsQuery.data;
    const alreadyQueued = (id: string) =>
      downloads.some(
        (item) =>
          item.source === sourceId &&
          item.series_id === seriesId &&
          item.chapter_id === id &&
          (ACTIVE_DOWNLOAD_STATES.includes(item.status) ||
            item.local_chapter_id != null),
      );

    const fresh = nextChapters.filter((chapter) => !alreadyQueued(chapter.id));
    if (fresh.length === 0) return;

    queueChapters
      .mutateAsync({
        source_id: sourceId,
        series_id: seriesId,
        chapter_ids: fresh.map((chapter) => chapter.id),
        chapter_titles: Object.fromEntries(
          fresh.map((chapter) => [chapter.id, chapter.title]),
        ),
      })
      .then((result) => {
        if (result.queued.length > 0) {
          setAutoQueueNotice(true);
          window.setTimeout(() => setAutoQueueNotice(false), 4000);
        }
      })
      .catch(() => {
        // Best-effort prefetch; failures are silent.
      });
  }, [
    chaptersQuery.data,
    downloadsQuery.data,
    chapterId,
    seriesId,
    sourceId,
    queueChapters,
  ]);

  useEffect(
    () => () => {
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current);
        progressTimerRef.current = null;
      }
    },
    [],
  );

  const handlePageProgress = useCallback(
    (page: number, pageCount: number) => {
      if (progressTimerRef.current) {
        clearTimeout(progressTimerRef.current);
      }
      progressTimerRef.current = window.setTimeout(() => {
        setSourceChapterProgress(sourceId, seriesId, chapterId, { page, pageCount });
        progressTimerRef.current = null;
      }, PROGRESS_SAVE_MS);
    },
    [sourceId, seriesId, chapterId],
  );

  const chapter = useMemo(
    () =>
      chapterQuery.data ? toRemoteReaderChapterContent(chapterQuery.data) : undefined,
    [chapterQuery.data],
  );

  const previousChapterHref = chapter?.previousChapterId
    ? sourceReaderChapterPath(sourceId, seriesId, chapter.previousChapterId)
    : null;
  const nextChapterHref = chapter?.nextChapterId
    ? sourceReaderChapterPath(sourceId, seriesId, chapter.nextChapterId)
    : null;

  return (
    <>
      {autoQueueNotice && (
        <div
          className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-full border border-border/60 bg-surface-2/90 px-4 py-2 text-sm text-fg shadow-lg backdrop-blur"
          role="status"
        >
          Downloading next chapters…
        </div>
      )}
      <ChapterReader
        chapter={chapter}
        isLoading={chapterQuery.isPending && chapterQuery.data === undefined}
        error={chapterQuery.error}
        scrollKey={`${sourceId}:${seriesId}:${chapterId}`}
        initialPage={initialPage}
        previousChapterHref={previousChapterHref}
        nextChapterHref={nextChapterHref}
        backHref={`/sources/${sourceId}/series/${encodeURIComponent(seriesId)}`}
        showBookmark={false}
        onPageProgress={handlePageProgress}
      />
    </>
  );
}
