"use client";

import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ensureChapterPages, useAddBookmark } from "../hooks";
import { readerChapterHref, seriesPageHref } from "../reader-link";
import { readerSeriesKey } from "../preferences";
import { chapterIndexOf, READER_STRIP_WINDOW } from "../strip";
import { linkedChapterSource } from "../strip-source";
import { useChapterStrip } from "../use-chapter-strip";
import { useStripProgress } from "../use-strip-progress";
import { ChapterReader } from "./ChapterReader";

interface SourceReaderProps {
  sourceId: string;
  seriesKey: string;
  chapterKey: string;
  initialPage?: number;
}

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

  const addBookmark = useAddBookmark();

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

  /**
   * Crossing a seam moves the chapter without a navigation, so the URL is
   * corrected in place: a refresh, a bookmark or a shared link still names the
   * chapter actually being read rather than the one the session started on.
   */
  const handleChapterChange = useCallback(
    (nextChapterKey: string) => {
      setActiveChapterKey(nextChapterKey);
      window.history.replaceState(
        window.history.state,
        "",
        readerChapterHref({ sourceId, seriesKey, chapterKey: nextChapterKey }),
      );
    },
    [seriesKey, sourceId],
  );

  const handlePosition = useStripProgress({
    sourceId,
    seriesKey,
    chapters,
    onChapterChange: handleChapterChange,
  });

  const handleBookmark = useCallback(
    (page: number) => {
      addBookmark.mutate({
        ref: { sourceId, seriesKey, chapterKey: activeChapterKey },
        page,
      });
    },
    [activeChapterKey, addBookmark, seriesKey, sourceId],
  );

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
      head={strip.head}
      tail={strip.tail}
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
