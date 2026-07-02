"use client";

import { useEffect, useMemo } from "react";
import { toRemoteReaderChapterContent } from "../api";
import { readerDebug } from "../debug";
import { ChapterReader } from "./ChapterReader";
import {
  sourceReaderChapterPath,
  useSourceReaderChapter,
} from "@/features/sources/hooks";

interface SourceReaderProps {
  sourceId: string;
  seriesId: string;
  chapterId: string;
  initialPage?: number;
}

export function SourceReader({
  sourceId,
  seriesId,
  chapterId,
  initialPage = 1,
}: SourceReaderProps) {
  const chapterQuery = useSourceReaderChapter(sourceId, seriesId, chapterId);

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
    />
  );
}
