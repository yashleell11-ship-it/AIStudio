"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useScrollContainer } from "@/lib/scroll-container";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useShortcut } from "@/lib/keyboard";
import { readerDebug } from "../debug";
import { estimateScrollOffsetToPage, resolveContainerWidth } from "../page-layout";
import { resolveInitialScrollTop, syncChapterScroll, clearChapterScrollPreparation } from "../scroll-preparation";
import { readScrollPosition, writeScrollPosition } from "../scroll-storage";
import { useReaderStore } from "../store";
import type { ReaderChapterContent } from "../types";
import { ChapterEdgePrompt, ReaderControls } from "./ReaderControls";
import { VirtualPageList } from "./VirtualPageList";

interface ChapterReaderProps {
  chapter: ReaderChapterContent | undefined;
  isLoading: boolean;
  error: unknown;
  scrollKey: string;
  initialPage?: number;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
  backHref: string;
  onBookmark?: (page: number) => void;
  onPageProgress?: (page: number, pageCount: number) => void;
  bookmarkPending?: boolean;
  showBookmark?: boolean;
}

const SCROLL_EDGE_THRESHOLD = 48;
const SCROLL_SAVE_MS = 250;

export function ChapterReader({
  chapter,
  isLoading,
  error,
  scrollKey,
  initialPage = 1,
  previousChapterHref,
  nextChapterHref,
  backHref,
  onBookmark,
  onPageProgress,
  bookmarkPending,
  showBookmark = true,
}: ChapterReaderProps) {
  const router = useRouter();
  const scrollElement = useScrollContainer();
  const zoom = useReaderStore((state) => state.zoomLevel);
  const zoomIn = useReaderStore((state) => state.zoomIn);
  const zoomOut = useReaderStore((state) => state.zoomOut);
  const resetZoom = useReaderStore((state) => state.resetZoom);
  const controlsVisible = useReaderStore((state) => state.controlsVisible);
  const toggleControls = useReaderStore((state) => state.toggleControls);
  const pageGap = useReaderStore((state) => state.pageGap);
  const togglePageGap = useReaderStore((state) => state.togglePageGap);

  const contentRef = useRef<HTMLDivElement>(null);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const bottomSentinelRef = useRef<HTMLDivElement>(null);
  const scrollSaveTimerRef = useRef<number | null>(null);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [visiblePage, setVisiblePage] = useState(Math.max(1, initialPage));
  const [atTop, setAtTop] = useState(false);
  const [atBottom, setAtBottom] = useState(false);

  const pages = useMemo(() => chapter?.pages ?? [], [chapter]);
  const chapterTitle = chapter?.title ?? "Chapter";

  const initialScrollTop = useMemo(() => {
    if (pages.length === 0) {
      return 0;
    }

    const containerWidth = resolveContainerWidth(scrollElement);
    const targetPage = Math.max(1, Math.min(initialPage, pages.length));
    return resolveInitialScrollTop({
      savedScroll: readScrollPosition(scrollKey),
      initialPage: targetPage,
      pageCount: pages.length,
      estimatedOffsetToPage: estimateScrollOffsetToPage(
        pages,
        targetPage,
        containerWidth,
        zoom,
      ),
    });
  }, [initialPage, pages, scrollElement, scrollKey, zoom]);

  useEffect(() => {
    return () => {
      if (scrollSaveTimerRef.current) {
        clearTimeout(scrollSaveTimerRef.current);
        scrollSaveTimerRef.current = null;
      }
      if (scrollElement) {
        writeScrollPosition(scrollKey, scrollElement.scrollTop);
      }
      clearChapterScrollPreparation(scrollKey);
    };
  }, [scrollElement, scrollKey]);

  useEffect(() => {
    readerDebug("route-entered", { scrollKey, initialPage, isLoading, hasChapter: Boolean(chapter) });
  }, [scrollKey, initialPage, isLoading, chapter]);

  useEffect(() => {
    if (isLoading) {
      readerDebug("loading-state", { scrollKey, reason: "chapter-pending" });
    }
  }, [isLoading, scrollKey]);

  useEffect(() => {
    if (!chapter) return;
    readerDebug("chapter-render-ready", {
      scrollKey,
      pagesLength: pages.length,
      title: chapter.title,
    });
  }, [chapter, pages.length, scrollKey]);

  useEffect(() => {
    readerDebug("reader-mounted", { scrollKey, scrollReady: Boolean(scrollElement) });
  }, [scrollKey, scrollElement]);

  const handleImagesReady = useCallback(() => {
    readerDebug("images-initialized", { scrollKey, pageCount: pages.length });
    readerDebug("reader-ready", {
      scrollKey,
      pageCount: pages.length,
      scrollReady: Boolean(scrollElement),
    });
  }, [pages.length, scrollElement, scrollKey]);

  const handleVisiblePageChange = useCallback(
    (pageNumber: number) => {
      setVisiblePage(pageNumber);
      onPageProgress?.(pageNumber, pages.length);
    },
    [onPageProgress, pages.length],
  );

  const updateScrollState = useCallback(() => {
    if (!scrollElement) return;

    const { scrollTop, scrollHeight, clientHeight } = scrollElement;
    const maxScroll = Math.max(scrollHeight - clientHeight, 0);
    const progress = maxScroll > 0 ? Math.round((scrollTop / maxScroll) * 100) : 100;
    setScrollProgress(progress);
    setAtTop(scrollTop <= SCROLL_EDGE_THRESHOLD);
    setAtBottom(scrollTop + clientHeight >= scrollHeight - SCROLL_EDGE_THRESHOLD);

    if (scrollSaveTimerRef.current) {
      clearTimeout(scrollSaveTimerRef.current);
    }
    scrollSaveTimerRef.current = window.setTimeout(() => {
      writeScrollPosition(scrollKey, scrollTop);
      scrollSaveTimerRef.current = null;
    }, SCROLL_SAVE_MS);
  }, [scrollElement, scrollKey]);

  useEffect(() => {
    if (!scrollElement) return;

    let frame = 0;
    const handleScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(updateScrollState);
    };

    handleScroll();
    scrollElement.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scrollElement.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(frame);
    };
  }, [scrollElement, updateScrollState]);

  useLayoutEffect(() => {
    if (isLoading || error || !chapter || pages.length === 0 || !scrollElement) {
      return;
    }
    syncChapterScroll(scrollKey, scrollElement, initialScrollTop);
  }, [
    chapter,
    error,
    initialScrollTop,
    isLoading,
    pages.length,
    scrollElement,
    scrollKey,
  ]);

  const goPreviousChapter = useCallback(() => {
    if (previousChapterHref) {
      router.push(previousChapterHref);
    }
  }, [previousChapterHref, router]);

  const goNextChapter = useCallback(() => {
    if (nextChapterHref) {
      router.push(nextChapterHref);
    }
  }, [nextChapterHref, router]);

  const handleBookmark = useCallback(() => {
    if (!showBookmark || !onBookmark) return;
    onBookmark(visiblePage);
  }, [onBookmark, showBookmark, visiblePage]);

  useShortcut({
    id: "reader.prev-chapter",
    keys: "h",
    description: "Previous chapter",
    group: "Reader",
    handler: goPreviousChapter,
  });

  useShortcut({
    id: "reader.next-chapter",
    keys: "l",
    description: "Next chapter",
    group: "Reader",
    handler: goNextChapter,
  });

  useShortcut({
    id: "reader.bookmark",
    keys: "b",
    description: "Bookmark current page",
    group: "Reader",
    handler: handleBookmark,
  });

  useShortcut({
    id: "reader.zoom-in",
    keys: ["=", "+", "shift+="],
    description: "Zoom in",
    group: "Reader",
    handler: zoomIn,
  });

  useShortcut({
    id: "reader.zoom-out",
    keys: "-",
    description: "Zoom out",
    group: "Reader",
    handler: zoomOut,
  });

  useShortcut({
    id: "reader.zoom-reset",
    keys: "0",
    description: "Reset zoom",
    group: "Reader",
    handler: resetZoom,
  });

  if (isLoading) {
    return (
      <div
        className="flex min-h-[60vh] flex-col items-center justify-center gap-4 bg-bg p-6"
        aria-busy="true"
        aria-label="Loading chapter"
      >
        <div className="w-full max-w-3xl space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="mx-auto aspect-[2/3] w-full max-w-md animate-pulse rounded-lg bg-white/5"
            />
          ))}
        </div>
        <p className="text-sm text-muted">Loading chapter…</p>
      </div>
    );
  }

  if (error) {
    const message =
      error instanceof ApiError ? error.message : "Failed to load chapter.";
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 bg-bg p-6 text-center">
        <p className="text-danger">{message}</p>
        <Link
          href={backHref}
          className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg transition-colors hover:bg-primary-hover"
        >
          Go back
        </Link>
      </div>
    );
  }

  if (!chapter || pages.length === 0) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center bg-bg text-muted">
        This chapter has no pages.
      </div>
    );
  }

  return (
    <div
      ref={contentRef}
      className="relative flex min-h-full flex-col bg-bg scroll-smooth"
      onClick={() => toggleControls()}
      role="presentation"
    >
      <div
        className={cn(
          "pointer-events-none fixed left-1/2 top-4 z-20 -translate-x-1/2 transition-opacity duration-300",
          controlsVisible ? "opacity-0" : "opacity-100",
        )}
      >
        <div className="glass-panel rounded-full px-4 py-1.5 font-mono text-xs tabular-nums text-primary">
          {visiblePage} <span className="text-muted">/ {pages.length}</span>
        </div>
      </div>

      <div className="flex-1 py-4 pb-28">
        <div ref={topSentinelRef} className="h-px w-full" aria-hidden />
        {atTop && previousChapterHref != null && (
          <ChapterEdgePrompt
            href={previousChapterHref}
            direction="previous"
            label="Previous chapter"
          />
        )}
        {scrollElement ? (
          <VirtualPageList
            key={scrollKey}
            pages={pages}
            chapterTitle={chapterTitle}
            zoom={zoom}
            pageGap={pageGap}
            scrollElement={scrollElement}
            initialScrollTop={initialScrollTop}
            onVisiblePageChange={handleVisiblePageChange}
            onImagesReady={handleImagesReady}
          />
        ) : null}
        {atBottom && nextChapterHref != null && (
          <ChapterEdgePrompt
            href={nextChapterHref}
            direction="next"
            label="Next chapter"
          />
        )}
        <div ref={bottomSentinelRef} className="h-px w-full" aria-hidden />
      </div>
      <div onClick={(event) => event.stopPropagation()} role="presentation">
        <ReaderControls
          chapterTitle={chapterTitle}
          scrollProgress={scrollProgress}
          visiblePage={visiblePage}
          pageCount={pages.length}
          zoom={zoom}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onZoomReset={resetZoom}
          pageGap={pageGap}
          onTogglePageGap={togglePageGap}
          onBookmark={onBookmark ? handleBookmark : undefined}
          previousChapterHref={previousChapterHref}
          nextChapterHref={nextChapterHref}
          backHref={backHref}
          bookmarkPending={bookmarkPending}
          showBookmark={showBookmark}
          visible={controlsVisible}
        />
      </div>
    </div>
  );
}
