"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useScrollContainer } from "@/lib/scroll-container";
import { cn } from "@/lib/cn";
import { moodReaderMargin, useActiveProfileStore } from "@/features/profiles";
import { OfflineChapterControl } from "@/features/offline";
import { ApiError } from "@/types/api";
import { readerDebug } from "../debug";
import { effectiveFitMode, wheelZoomSteps, zoomBy } from "../fit";
import { resolveEscapeTarget, type PageTurn, type TapZone } from "../keymap";
import { estimateScrollOffsetToPage, resolveContainerWidth } from "../page-layout";
import {
  clearChapterScrollPreparation,
  resolveInitialScrollTop,
  scrollReaderBy,
  setReaderScrollTop,
  syncChapterScroll,
} from "../scroll-preparation";
import { readScrollPosition, writeScrollPosition } from "../scroll-storage";
import { scrubPercent } from "../scrub";
import { buildPageViews, findViewIndex, viewLeadPage } from "../spread";
import { useReaderStore } from "../store";
import { useCinema } from "../use-cinema";
import { useChapterPreload } from "../use-chapter-preload";
import { useFullscreen } from "../use-fullscreen";
import { useReaderPreferences } from "../use-reader-preferences";
import { useReaderSettings } from "../use-reader-settings";
import { useReaderShortcuts } from "../use-reader-shortcuts";
import type { ReaderChapterContent, ReadingMode } from "../types";
import { PagedView } from "./PagedView";
import { ChapterEdgePrompt, ReaderControls } from "./ReaderControls";
import { ShortcutsOverlay } from "./ShortcutsOverlay";
import { VirtualPageList } from "./VirtualPageList";

interface ChapterReaderProps {
  chapter: ReaderChapterContent | undefined;
  isLoading: boolean;
  error: unknown;
  scrollKey: string;
  /** Identifies the series whose reading mode / fit / zoom this reader restores. */
  seriesKey: string;
  initialPage?: number;
  previousChapterHref: string | null;
  nextChapterHref: string | null;
  /**
   * This chapter's own series page. It is both where the reader exits to and
   * where the "Series" control jumps, so a chapter opened from search, Updates
   * or a deep link still reaches its chapter list without retracing history.
   */
  seriesHref: string;
  onBookmark?: (page: number) => void;
  onPageProgress?: (page: number, pageCount: number) => void;
  /** Resolves the next chapter's payload so the reader can pull it early. */
  preloadNextChapter?: () => Promise<ReadonlyArray<{ imageUrl: string }>>;
  bookmarkPending?: boolean;
  showBookmark?: boolean;
}

const SCROLL_EDGE_THRESHOLD = 48;
const SCROLL_SAVE_MS = 250;
/** Fraction of the viewport a Space press travels, leaving an overlap to re-read. */
const SCREEN_SCROLL_RATIO = 0.9;

/** Stable no-op so `useChapterPreload` is not re-armed by an identity change. */
const NO_PRELOAD = async (): Promise<ReadonlyArray<{ imageUrl: string }>> => [];

/** Stable placeholder view for the frame before any page is known. */
const FIRST_PAGE_VIEW = [1];

export function ChapterReader({
  chapter,
  isLoading,
  error,
  scrollKey,
  seriesKey,
  initialPage = 1,
  previousChapterHref,
  nextChapterHref,
  seriesHref,
  onBookmark,
  onPageProgress,
  preloadNextChapter,
  bookmarkPending,
  showBookmark = true,
}: ChapterReaderProps) {
  const router = useRouter();
  const scrollElement = useScrollContainer();
  const controlsVisible = useReaderStore((state) => state.controlsVisible);
  const toggleControls = useReaderStore((state) => state.toggleControls);
  const setControlsVisible = useReaderStore((state) => state.setControlsVisible);
  const { pageGap, cinema, togglePageGap, setCinema } = useReaderSettings();

  const {
    readingMode,
    fitMode,
    direction,
    zoom,
    hydrated: preferencesReady,
    update: updatePreferences,
  } = useReaderPreferences(seriesKey);
  const fullscreen = useFullscreen();

  const scrollSaveTimerRef = useRef<number | null>(null);
  const scrollToPageRef = useRef<((pageNumber: number) => void) | null>(null);
  const pendingScrollPageRef = useRef<number | null>(null);
  const readingModeRef = useRef(readingMode);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [visiblePage, setVisiblePage] = useState(Math.max(1, initialPage));
  const [atTop, setAtTop] = useState(false);
  const [atBottom, setAtBottom] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  const pages = useMemo(() => chapter?.pages ?? [], [chapter]);
  const chapterTitle = chapter?.title ?? "Chapter";
  const continuous = readingMode === "continuous";

  // Ambient mood tint, but only in the gutters beside the page column — the page
  // itself stays pure obsidian. `default` mood → "transparent" → no wash.
  const mood = useActiveProfileStore((state) => state.activeProfile?.mood ?? "default");
  const marginWash = moodReaderMargin(mood);
  const gutterBackground =
    marginWash === "transparent"
      ? undefined
      : `linear-gradient(90deg, ${marginWash} 0%, transparent calc((100% - 48rem) / 2), transparent calc(100% - (100% - 48rem) / 2), ${marginWash} 100%)`;

  const cinemaCtl = useCinema({
    persistedEnabled: cinema,
    scrollElement,
    active: Boolean(chapter) && !isLoading && !error,
    onEnabledChange: setCinema,
  });

  // The chrome follows cinema mode while it is engaged; otherwise the plain
  // tap-to-toggle store value. Turning cinema off always leaves the chrome up.
  const chromeVisible = cinemaCtl.enabled ? cinemaCtl.chromeVisible : controlsVisible;
  const toggleCinema = useCallback(() => {
    cinemaCtl.toggle();
    if (cinemaCtl.enabled) setControlsVisible(true);
  }, [cinemaCtl, setControlsVisible]);

  useEffect(() => {
    readingModeRef.current = readingMode;
  }, [readingMode]);

  const views = useMemo(
    () => buildPageViews(pages.length, readingMode),
    [pages.length, readingMode],
  );
  const viewIndex = useMemo(() => findViewIndex(views, visiblePage), [views, visiblePage]);
  const currentView = views[viewIndex];

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

  /**
   * Where to resume this chapter, resolved at the moment the reader leaves.
   *
   * The strip reports its live offset, exactly as before. A paged mode has none
   * — the container never scrolls — so it reports the offset its current page
   * would occupy in the strip. Saving the container's literal 0 instead would
   * wipe the chapter's restore point the first time anyone opened it as pages.
   */
  const scrollAnchorRef = useRef<() => number | null>(() => null);
  useEffect(() => {
    scrollAnchorRef.current = () => {
      if (!scrollElement) return null;
      if (readingModeRef.current === "continuous") return scrollElement.scrollTop;
      if (pages.length === 0) return null;
      return estimateScrollOffsetToPage(
        pages,
        visiblePage,
        resolveContainerWidth(scrollElement),
        zoom,
      );
    };
  }, [pages, scrollElement, visiblePage, zoom]);

  useEffect(() => {
    return () => {
      if (scrollSaveTimerRef.current) {
        clearTimeout(scrollSaveTimerRef.current);
        scrollSaveTimerRef.current = null;
      }
      const anchor = scrollAnchorRef.current();
      if (anchor != null) {
        writeScrollPosition(scrollKey, anchor);
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

  const registerScrollToPage = useCallback(
    (scrollToPage: ((pageNumber: number) => void) | null) => {
      scrollToPageRef.current = scrollToPage;
      // A pending target means the strip was just re-entered from a paged mode.
      // Consume it on the first registration — the list has mounted and its own
      // restore has already run, so this is the last word on where to land.
      const pending = pendingScrollPageRef.current;
      if (scrollToPage && pending != null) {
        pendingScrollPageRef.current = null;
        scrollToPage(pending);
      }
    },
    [],
  );

  const updateScrollState = useCallback(() => {
    if (!scrollElement) return;
    if (readingModeRef.current !== "continuous") return;

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

  const goToPage = useCallback(
    (pageNumber: number) => {
      if (pages.length === 0) return;
      const target = Math.min(pages.length, Math.max(1, Math.round(pageNumber)));
      setVisiblePage(target);
      onPageProgress?.(target, pages.length);

      if (readingMode !== "continuous") return;

      // The virtualizer knows the measured page heights; the estimator is only
      // the fallback for the frame before it has published its jump.
      const scrollToPage = scrollToPageRef.current;
      if (scrollToPage) {
        scrollToPage(target);
      } else {
        setReaderScrollTop(
          scrollElement,
          estimateScrollOffsetToPage(
            pages,
            target,
            resolveContainerWidth(scrollElement),
            zoom,
          ),
        );
      }
    },
    [onPageProgress, pages, readingMode, scrollElement, zoom],
  );

  const turnPage = useCallback(
    (turn: PageTurn) => {
      if (pages.length === 0) return;
      const step = turn === "advance" ? 1 : -1;

      if (readingMode === "continuous") {
        goToPage(visiblePage + step);
        return;
      }

      // Paged modes have a hard edge, so a turn past it continues into the
      // neighbouring chapter — the payload is already warm by then.
      const nextIndex = viewIndex + step;
      if (nextIndex < 0) {
        goPreviousChapter();
        return;
      }
      if (nextIndex >= views.length) {
        goNextChapter();
        return;
      }
      goToPage(viewLeadPage(views[nextIndex]));
    },
    [
      goNextChapter,
      goPreviousChapter,
      goToPage,
      pages.length,
      readingMode,
      viewIndex,
      views,
      visiblePage,
    ],
  );

  const scrollScreen = useCallback(
    (turn: PageTurn) => {
      if (readingMode !== "continuous") {
        turnPage(turn);
        return;
      }
      if (!scrollElement) return;
      const delta = Math.max(160, scrollElement.clientHeight * SCREEN_SCROLL_RATIO);
      scrollReaderBy(scrollElement, turn === "advance" ? delta : -delta);
    },
    [readingMode, scrollElement, turnPage],
  );

  const handleTap = useCallback(
    (zone: TapZone) => {
      if (zone === "toggle") {
        // In cinema mode a tap reveals the chrome (and re-arms the idle timer)
        // rather than latching it on/off — the timeout owns hiding it again.
        if (cinemaCtl.enabled) cinemaCtl.notifyActivity();
        else toggleControls();
        return;
      }
      turnPage(zone);
    },
    [cinemaCtl, toggleControls, turnPage],
  );

  const handleBookmark = useCallback(() => {
    if (!showBookmark || !onBookmark) return;
    onBookmark(visiblePage);
  }, [onBookmark, showBookmark, visiblePage]);

  const zoomIn = useCallback(
    () => updatePreferences({ zoom: zoomBy(zoom, 1) }),
    [updatePreferences, zoom],
  );
  const zoomOut = useCallback(
    () => updatePreferences({ zoom: zoomBy(zoom, -1) }),
    [updatePreferences, zoom],
  );
  const resetZoom = useCallback(() => updatePreferences({ zoom: 1 }), [updatePreferences]);
  const zoomSteps = useCallback(
    (steps: number) => updatePreferences({ zoom: zoomBy(zoom, steps) }),
    [updatePreferences, zoom],
  );

  /**
   * Switching back to the strip lands on the page that was on screen instead of
   * wherever the strip happened to be left. The target is queued rather than
   * applied here: the list has not mounted yet, and it hands back a jump that
   * uses measured page heights as soon as it has.
   */
  const changeReadingMode = useCallback(
    (mode: ReadingMode) => {
      if (mode === readingMode) return;
      if (mode === "continuous" && pages.length > 0) {
        pendingScrollPageRef.current = visiblePage;
        // The edge prompts are driven by scroll state the paged modes never
        // update; clear them so a stale flag cannot greet the returning strip.
        setAtTop(false);
        setAtBottom(false);
      }
      updatePreferences({ readingMode: mode });
    },
    [pages.length, readingMode, updatePreferences, visiblePage],
  );

  // Same wheel contract as the paged stage: ctrl/⌘+wheel zooms, a plain wheel
  // scrolls. Non-passive so the browser's own page zoom can be cancelled.
  useEffect(() => {
    if (!scrollElement || !continuous) return;

    const handleWheel = (event: WheelEvent) => {
      const steps = wheelZoomSteps(event);
      if (steps === 0) return;
      event.preventDefault();
      zoomSteps(steps);
    };

    scrollElement.addEventListener("wheel", handleWheel, { passive: false });
    return () => scrollElement.removeEventListener("wheel", handleWheel);
  }, [continuous, scrollElement, zoomSteps]);

  const handleEscape = useCallback(() => {
    switch (resolveEscapeTarget({ helpOpen, fullscreen: fullscreen.active })) {
      case "help":
        setHelpOpen(false);
        return;
      case "fullscreen":
        fullscreen.exit();
        return;
      default:
        // Peel cinema mode before leaving the reader, so Escape doesn't drop
        // the reader and the immersive chrome in one press.
        if (cinemaCtl.enabled) {
          toggleCinema();
          return;
        }
        router.push(seriesHref);
    }
  }, [cinemaCtl.enabled, fullscreen, helpOpen, router, seriesHref, toggleCinema]);

  /**
   * Leave the chapter for its series page.
   *
   * Fullscreen belongs to the document, not to the reader, so it survives a
   * client-side navigation: without dropping it first the chapter list would
   * open in a fullscreened window with no browser chrome to get out of.
   */
  const openSeries = useCallback(() => {
    fullscreen.exit();
    router.push(seriesHref);
  }, [fullscreen, router, seriesHref]);

  useReaderShortcuts({
    direction,
    onTurnPage: turnPage,
    onScrollScreen: scrollScreen,
    onFirstPage: () => goToPage(1),
    onLastPage: () => goToPage(pages.length),
    onToggleFullscreen: fullscreen.toggle,
    onToggleCinema: toggleCinema,
    onEscape: handleEscape,
    onToggleHelp: () => setHelpOpen((open) => !open),
    onPreviousChapter: goPreviousChapter,
    onNextChapter: goNextChapter,
    onOpenSeries: openSeries,
    onBookmark: handleBookmark,
    onZoomIn: zoomIn,
    onZoomOut: zoomOut,
    onZoomReset: resetZoom,
  });

  useChapterPreload({
    chapterKey: scrollKey,
    page: visiblePage,
    pageCount: pages.length,
    hasNextChapter: nextChapterHref != null && preloadNextChapter != null,
    loadNextChapter: preloadNextChapter ?? NO_PRELOAD,
  });

  if (isLoading || !preferencesReady) {
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
          href={seriesHref}
          className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg transition-colors hover:bg-primary-hover"
        >
          Go to series
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
      className={cn(
        "relative flex flex-col bg-bg",
        continuous ? "min-h-full scroll-smooth" : "h-full overflow-hidden",
      )}
      style={gutterBackground ? { background: gutterBackground } : undefined}
      // The paged view owns its own clicks (edge zones turn the page), so the
      // tap-anywhere toggle is wired only for the strip.
      onClick={
        continuous
          ? () => {
              if (cinemaCtl.enabled) cinemaCtl.notifyActivity();
              else toggleControls();
            }
          : undefined
      }
      role="presentation"
    >
      {/*
        Saves this chapter's pages to the device, using the very URLs resolved
        above — the reader's own page loading is untouched, the service worker
        just answers those requests from the cache when the network is gone.
      */}
      <div onClick={(event) => event.stopPropagation()} role="presentation">
        <OfflineChapterControl
          chapter={chapter}
          visiblePage={visiblePage}
          visible={chromeVisible}
        />
      </div>

      <div
        className={cn(
          "pointer-events-none fixed left-1/2 top-4 z-20 -translate-x-1/2",
          cinemaCtl.reducedMotion ? "" : "transition-opacity duration-300",
          // Cinema mode hides even this: revealed activity brings the full
          // control bar (which carries the page count) back instead.
          !chromeVisible && !cinemaCtl.enabled ? "opacity-100" : "opacity-0",
        )}
      >
        <div className="glass-panel rounded-full px-4 py-1.5 font-mono text-xs tabular-nums text-primary">
          {visiblePage} <span className="text-muted">/ {pages.length}</span>
        </div>
      </div>

      {continuous ? (
        <div className="flex-1 py-4 pb-28">
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
              onScrollToPageReady={registerScrollToPage}
            />
          ) : null}
          {atBottom && nextChapterHref != null && (
            <ChapterEdgePrompt
              href={nextChapterHref}
              direction="next"
              label="Next chapter"
            />
          )}
        </div>
      ) : (
        <PagedView
          pages={pages}
          chapterTitle={chapterTitle}
          view={currentView ?? FIRST_PAGE_VIEW}
          slotsPerView={readingMode === "double" ? 2 : 1}
          direction={direction}
          fitMode={effectiveFitMode(fitMode, readingMode)}
          zoom={zoom}
          onTap={handleTap}
          onZoom={zoomSteps}
        />
      )}

      <div onClick={(event) => event.stopPropagation()} role="presentation">
        <ReaderControls
          chapterTitle={chapterTitle}
          scrollProgress={
            continuous ? scrollProgress : Math.round(scrubPercent(visiblePage, pages.length))
          }
          visiblePage={visiblePage}
          pageCount={pages.length}
          zoom={zoom}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onZoomReset={resetZoom}
          readingMode={readingMode}
          onReadingModeChange={changeReadingMode}
          fitMode={fitMode}
          onFitModeChange={(mode) => updatePreferences({ fitMode: mode })}
          direction={direction}
          onDirectionChange={(next) => updatePreferences({ direction: next })}
          onSeekPage={goToPage}
          fullscreen={fullscreen.active}
          fullscreenSupported={fullscreen.supported}
          onToggleFullscreen={fullscreen.toggle}
          onShowShortcuts={() => setHelpOpen(true)}
          pageGap={pageGap}
          onTogglePageGap={continuous ? togglePageGap : undefined}
          cinema={cinemaCtl.enabled}
          onToggleCinema={toggleCinema}
          onBookmark={onBookmark ? handleBookmark : undefined}
          previousChapterHref={previousChapterHref}
          nextChapterHref={nextChapterHref}
          seriesHref={seriesHref}
          onOpenSeries={openSeries}
          bookmarkPending={bookmarkPending}
          showBookmark={showBookmark}
          visible={chromeVisible}
        />
        <ShortcutsOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
      </div>
    </div>
  );
}
