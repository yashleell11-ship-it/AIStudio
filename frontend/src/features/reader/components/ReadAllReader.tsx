"use client";

import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSourceChapters } from "@/features/sources/hooks";
import {
  BOOKMARK_MEDIA_MANGA,
  useBookmarkCapture,
} from "@/features/bookmarks";
import { readAllHref, seriesPageHref } from "../reader-link";
import { readerSeriesKey } from "../preferences";
import { orderIndexOf, readAllEntryKey, readingOrder } from "../read-all";
import { chapterIndexOf, READ_ALL_STRIP_WINDOW } from "../strip";
import { bulkChapterSource } from "../strip-source";
import { useChapterStrip } from "../use-chapter-strip";
import { useStripProgress } from "../use-strip-progress";
import { ChapterReader, type CapturedAnchor } from "./ChapterReader";

interface ReadAllReaderProps {
  sourceId: string;
  seriesKey: string;
  /** Where to start the run. Absent means the first chapter of the series. */
  fromChapterKey?: string | null;
  initialPage?: number;
  /** `?at=` — the fraction of `initialPage` a bookmark link is opening at. */
  initialAnchorFraction?: number | null;
}

/**
 * The whole series as one scroll (spec 2026-09-05 R2).
 *
 * > "if it have 30 chapter ill watch it in 1 chapter without feeling it"
 *
 * The same strip the plain reader uses, fed differently: the series' own
 * chapter list gives the reading order (a connector that lists newest-first
 * cannot send the run backwards), and `POST /reader/chapters/manifest` pulls a
 * window of chapters per round trip instead of one, which is what lets a
 * three-hundred-chapter series open in the time of a normal chapter and fill in
 * behind. Nothing about the rendering differs — the strip virtualises its rows
 * and releases the chapters the reader has left behind, so the DOM holds a
 * handful of pages however far into the series the run gets.
 *
 * Progress is the ordinary per-chapter progress: reading into chapter 12
 * records chapter 12, so leaving and resuming lands correctly and the
 * furthest-wins merge is untouched.
 */
export function ReadAllReader({
  sourceId,
  seriesKey,
  fromChapterKey = null,
  initialPage = 1,
  initialAnchorFraction = null,
}: ReadAllReaderProps) {
  const queryClient = useQueryClient();
  const chaptersQuery = useSourceChapters(sourceId, seriesKey);

  const order = useMemo(
    () => readingOrder(chaptersQuery.data ?? []),
    [chaptersQuery.data],
  );
  const entryChapterKey = useMemo(
    () => readAllEntryKey(order, fromChapterKey) ?? "",
    [order, fromChapterKey],
  );

  const [activeChapterKey, setActiveChapterKey] = useState("");
  const source = useMemo(
    () => bulkChapterSource(queryClient, sourceId, seriesKey, order),
    [order, queryClient, seriesKey, sourceId],
  );

  const strip = useChapterStrip({
    entryChapterKey,
    activeChapterKey: activeChapterKey || entryChapterKey,
    source,
    window: READ_ALL_STRIP_WINDOW,
    // Nothing can be named before the chapter list arrives; until then this is
    // the series page's own request, already in flight or already cached.
    ready: order.length > 0 && entryChapterKey !== "",
  });

  const bookmark = useBookmarkCapture();
  const chapters = strip.chapters;

  /**
   * The run's URL names the chapter being read, so a refresh resumes there
   * rather than at the top of the series — the same trick the plain reader
   * plays, and the reason `?from=` exists at all.
   */
  const handleChapterChange = useCallback(
    (nextChapterKey: string) => {
      setActiveChapterKey(nextChapterKey);
      window.history.replaceState(
        window.history.state,
        "",
        readAllHref({ sourceId, seriesKey }, nextChapterKey),
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

  /**
   * Same capture as the plain reader, against whichever chapter the run has
   * reached — a bookmark taken forty chapters into a read-all belongs to
   * chapter forty, not to the one the run started on.
   */
  const handleBookmark = useCallback(
    (anchor: CapturedAnchor) => {
      const chapterKey = activeChapterKey || entryChapterKey;
      if (!chapterKey) return;
      bookmark.capture({
        source_id: sourceId,
        series_key: seriesKey,
        chapter_key: chapterKey,
        chapter_number: chapters[chapterIndexOf(chapters, chapterKey)]?.chapterNumber ?? null,
        media_type: BOOKMARK_MEDIA_MANGA,
        anchor_index: anchor.index,
        anchor_fraction: anchor.fraction,
        anchor_total: anchor.total,
      });
    },
    [activeChapterKey, bookmark, chapters, entryChapterKey, seriesKey, sourceId],
  );

  /**
   * "13 of 40" — the one thing a run through a whole series needs that reading
   * a single chapter does not: some sense of where in the book you are. The
   * chapter's own title is not it when there are three hundred of them.
   */
  const positionInSeries = orderIndexOf(order, activeChapterKey || entryChapterKey);
  const chapterPosition =
    positionInSeries >= 0 ? `${positionInSeries + 1} of ${order.length}` : null;

  const listFailed =
    chaptersQuery.isError || (!chaptersQuery.isLoading && order.length === 0);

  return (
    <ChapterReader
      chapters={chapters}
      entryChapterKey={entryChapterKey}
      isLoading={strip.isLoading && !listFailed}
      error={
        listFailed
          ? "This series' chapter list didn't come through, so there is nothing to read through."
          : strip.error
      }
      onRetry={listFailed ? () => void chaptersQuery.refetch() : strip.reload}
      seriesKey={readerSeriesKey(sourceId, seriesKey)}
      initialPage={initialPage}
      seriesHref={seriesPageHref({ sourceId, seriesKey })}
      head={strip.head}
      tail={strip.tail}
      chapterPosition={chapterPosition}
      onPosition={handlePosition}
      onBookmark={handleBookmark}
      initialAnchorFraction={initialAnchorFraction}
      bookmarkSaved={bookmark.justSaved}
      bookmarkFailed={bookmark.failed}
      onLoadPrevious={strip.loadPrevious}
      loadingPrevious={strip.loadingPrevious}
      nextError={strip.nextError}
      onRetryNext={strip.retryNext}
      bookmarkPending={bookmark.pending}
      showBookmark
    />
  );
}
