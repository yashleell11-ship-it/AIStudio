"use client";

import { useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BOOKMARK_MEDIA_MANGA,
  useBookmarkCapture,
} from "@/features/bookmarks";
import { ensureChapterPages } from "../hooks";
import { readerChapterHref, seriesPageHref } from "../reader-link";
import { readerSeriesKey } from "../preferences";
import { chapterIndexOf, READER_STRIP_WINDOW } from "../strip";
import { linkedChapterSource } from "../strip-source";
import { useChapterStrip } from "../use-chapter-strip";
import { useStripProgress } from "../use-strip-progress";
import { ChapterReader, type CapturedAnchor } from "./ChapterReader";

interface SourceReaderProps {
  sourceId: string;
  seriesKey: string;
  chapterKey: string;
  initialPage?: number;
  /** `?at=` — the fraction of `initialPage` a bookmark link is opening at. */
  initialAnchorFraction?: number | null;
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
  initialAnchorFraction = null,
}: SourceReaderProps) {
  const queryClient = useQueryClient();

  // The chapter actually being read. Starts at the routed key; crossing a seam
  // moves it with no navigation at all.
  const [activeChapterKey, setActiveChapterKey] = useState(chapterKey);

  // A real navigation (route change, refresh, deep link) normally remounts via
  // the page's `key`, but follow the props during render anyway if they change
  // under us — the accepted "reset state on prop change" pattern.
  const [routed, setRouted] = useState({
    chapterKey,
    initialPage,
    initialAnchorFraction,
  });
  if (
    routed.chapterKey !== chapterKey ||
    routed.initialPage !== initialPage ||
    routed.initialAnchorFraction !== initialAnchorFraction
  ) {
    setRouted({ chapterKey, initialPage, initialAnchorFraction });
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

  const bookmark = useBookmarkCapture();

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

  /**
   * One deliberate marker at the exact spot being read.
   *
   * The anchor arrives already resolved against the ACTIVE chapter — the strip
   * moves that without a navigation — so the chapter identity here is
   * `activeChapterKey`, never the key the route opened on. `chapter_number`
   * rides along so the bookmark still means something if the source re-keys
   * its chapters (design §3).
   */
  const handleBookmark = useCallback(
    (anchor: CapturedAnchor) => {
      bookmark.capture({
        source_id: sourceId,
        series_key: seriesKey,
        chapter_key: activeChapterKey,
        chapter_number: activeChapter?.chapterNumber ?? null,
        media_type: BOOKMARK_MEDIA_MANGA,
        anchor_index: anchor.index,
        anchor_fraction: anchor.fraction,
        anchor_total: anchor.total,
      });
    },
    [activeChapter?.chapterNumber, activeChapterKey, bookmark, seriesKey, sourceId],
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
      initialAnchorFraction={routed.initialAnchorFraction}
      bookmarkSaved={bookmark.justSaved}
      bookmarkFailed={bookmark.failed}
      onLoadPrevious={strip.loadPrevious}
      loadingPrevious={strip.loadingPrevious}
      nextError={strip.nextError}
      onRetryNext={strip.retryNext}
      preloadNextChapter={preloadNextChapter}
      bookmarkPending={bookmark.pending}
      showBookmark
    />
  );
}
