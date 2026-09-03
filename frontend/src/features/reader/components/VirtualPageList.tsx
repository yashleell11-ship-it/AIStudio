"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { readerDebug } from "../debug";
import { continuousPageSizing } from "../fit";
import type { ReaderPage } from "../types";
import {
  DEFAULT_CONTAINER_WIDTH,
  estimatePageHeight,
  resolveContainerWidth,
} from "../page-layout";
import {
  EMPTY_HEIGHT_SAMPLES,
  estimateFromSamples,
  recordHeight,
  type HeightSamples,
} from "../page-metrics";
import { PRELOAD_AHEAD_CONTINUOUS } from "../preload";
import { restoreChapterScroll } from "../scroll-preparation";
import { PageImage } from "./PageImage";

/**
 * Upcoming pages warmed into the browser cache ahead of the reader. The strip
 * looks the furthest ahead of any mode (see `pagesAheadToWarm`).
 */
const PREFETCH_AHEAD = PRELOAD_AHEAD_CONTINUOUS;

/** The thin separator height (`pb-2` = 0.5rem) when the page-gap setting is on. */
const PAGE_GAP_PX = 8;

/** Re-measure the virtualizer when the running average shifts more than this. */
const ESTIMATE_DRIFT_RATIO = 0.12;

interface VirtualPageRowProps {
  page: ReaderPage;
  pageNumber: number;
  chapterTitle: string;
  zoom: number;
  priority: boolean;
  pageGap: boolean;
  onImageLoad: () => void;
}

const VirtualPageRow = memo(function VirtualPageRow({
  page,
  pageNumber,
  chapterTitle,
  zoom,
  priority,
  pageGap,
  onImageLoad,
}: VirtualPageRowProps) {
  const sizing = continuousPageSizing(zoom);
  return (
    <div
      id={`reader-page-${pageNumber}`}
      data-page={pageNumber}
      // No bottom padding by default so consecutive pages stack flush — a webtoon
      // strip must read as one continuous image with no seam between pages.
      className={cn("mx-auto w-full", pageGap && "pb-2")}
      style={sizing}
    >
      <PageImage
        imageUrl={page.imageUrl}
        alt={`${chapterTitle} page ${pageNumber}`}
        width={page.width}
        height={page.height}
        priority={priority}
        seamless={!pageGap}
        onLoad={onImageLoad}
      />
    </div>
  );
});

interface VirtualPageListProps {
  pages: ReaderPage[];
  chapterTitle: string;
  zoom: number;
  pageGap: boolean;
  scrollElement: HTMLElement;
  initialScrollTop: number;
  onVisiblePageChange: (pageNumber: number) => void;
  onImagesReady?: () => void;
  /**
   * Hands the parent a precise jump-to-page. The scrubber must land on the page
   * it points at, and only the virtualizer knows the measured page heights —
   * the parent's estimator drifts on long chapters with unknown dimensions.
   */
  onScrollToPageReady?: (scrollToPage: ((pageNumber: number) => void) | null) => void;
}

export function VirtualPageList({
  pages,
  chapterTitle,
  zoom,
  pageGap,
  scrollElement,
  initialScrollTop,
  onVisiblePageChange,
  onImagesReady,
  onScrollToPageReady,
}: VirtualPageListProps) {
  const [containerWidth, setContainerWidth] = useState(DEFAULT_CONTAINER_WIDTH);
  const readyNotifiedRef = useRef(false);
  const initialRestorePendingRef = useRef(initialScrollTop > 0);
  const prefetchedRef = useRef<Set<string>>(new Set());
  // Measured page heights fed back into `estimateSize` so the strip's total
  // height stops lurching as unmeasured (dimensionless webtoon) pages scroll in.
  const heightSamplesRef = useRef<HeightSamples>(EMPTY_HEIGHT_SAMPLES);
  const measuredByKeyRef = useRef<Map<string | number, number>>(new Map());
  const lastAvgEstimateRef = useRef(0);

  useLayoutEffect(() => {
    const measure = () => {
      setContainerWidth(resolveContainerWidth(scrollElement));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scrollElement);
    return () => observer.disconnect();
  }, [scrollElement]);

  useEffect(() => {
    readyNotifiedRef.current = false;
    initialRestorePendingRef.current = initialScrollTop > 0;
    prefetchedRef.current = new Set();
    heightSamplesRef.current = EMPTY_HEIGHT_SAMPLES;
    measuredByKeyRef.current = new Map();
    lastAvgEstimateRef.current = 0;
  }, [initialScrollTop, pages]);

  const prefetchAhead = useCallback(
    (activeIndex: number) => {
      if (typeof window === "undefined") return;
      const seen = prefetchedRef.current;
      for (let offset = 1; offset <= PREFETCH_AHEAD; offset += 1) {
        const next = pages[activeIndex + offset];
        if (!next || seen.has(next.imageUrl)) continue;
        seen.add(next.imageUrl);
        const preloader = new window.Image();
        preloader.decoding = "async";
        preloader.src = next.imageUrl;
      }
    },
    [pages],
  );

  useEffect(() => {
    readerDebug("virtual-page-list-mounted", {
      pagesLength: pages.length,
      scrollReady: true,
      containerWidth,
      measuredWidth: scrollElement.clientWidth,
    });
  }, [containerWidth, pages.length, scrollElement]);

  // TanStack Virtual returns fresh functions each render that cannot be memoized.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: pages.length,
    getScrollElement: () => scrollElement,
    estimateSize: (index) => {
      const key = pages[index]?.id ?? index;
      const measured = measuredByKeyRef.current.get(key);
      if (measured != null) return measured;
      const fallback =
        estimatePageHeight(pages[index], containerWidth, zoom) +
        (pageGap ? PAGE_GAP_PX : 0);
      return estimateFromSamples(heightSamplesRef.current, fallback);
    },
    overscan: 4,
    getItemKey: (index) => pages[index]?.id ?? index,
  });

  const virtualItems = virtualizer.getVirtualItems();

  useLayoutEffect(() => {
    if (pages.length === 0) return;
    virtualizer.measure();
    if (initialRestorePendingRef.current && initialScrollTop > 0) {
      if (scrollElement.scrollTop !== initialScrollTop) {
        const restored = restoreChapterScroll(scrollElement, initialScrollTop);
        if (restored) {
          virtualizer.measure();
        }
      }
      if (scrollElement.scrollTop === initialScrollTop) {
        initialRestorePendingRef.current = false;
      }
    }
    const visibleCount = virtualizer.getVirtualItems().length;
    readerDebug("virtualizer-ready", {
      pageCount: pages.length,
      visibleCount,
      totalSize: virtualizer.getTotalSize(),
      containerWidth,
      initialScrollTop,
      scrollTop: scrollElement.scrollTop,
    });
    // virtualizer identity changes each render; remeasure when layout inputs change.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [containerWidth, initialScrollTop, pages.length, scrollElement, zoom]);

  // No dependency array on purpose: the virtualizer is re-read every render so
  // the published callback always closes over current measurements.
  useEffect(() => {
    if (!onScrollToPageReady) return;
    onScrollToPageReady((pageNumber: number) => {
      if (pages.length === 0) return;
      const index = Math.min(pages.length - 1, Math.max(0, Math.round(pageNumber) - 1));
      virtualizer.scrollToIndex(index, { align: "start" });
    });
    return () => onScrollToPageReady(null);
  });

  const notifyReady = useCallback(() => {
    if (readyNotifiedRef.current) return;
    readyNotifiedRef.current = true;
    onImagesReady?.();
  }, [onImagesReady]);

  /**
   * Fold a page's real rendered height into the running average that backs
   * `estimateSize`. When the average has moved far enough that off-screen
   * estimates are now visibly wrong, ask the virtualizer to recompute — this
   * converges after the first handful of pages and then goes quiet.
   */
  const recordMeasuredHeight = useCallback(
    (key: string, height: number) => {
      if (!(height > 0)) return;
      const previous = measuredByKeyRef.current.get(key);
      if (previous != null && Math.abs(previous - height) < 1) return;
      measuredByKeyRef.current.set(key, height);
      heightSamplesRef.current = recordHeight(
        heightSamplesRef.current,
        previous,
        height,
      );
      const avg = estimateFromSamples(heightSamplesRef.current, height);
      const last = lastAvgEstimateRef.current;
      if (last === 0 || Math.abs(avg - last) / last > ESTIMATE_DRIFT_RATIO) {
        lastAvgEstimateRef.current = avg;
        virtualizer.measure();
      }
    },
    [virtualizer],
  );

  const reportVisiblePage = useCallback(() => {
    if (pages.length === 0) return;

    const scrollTop = scrollElement.scrollTop;
    const items = virtualizer.getVirtualItems();
    if (items.length === 0) return;

    let activeIndex = items[0].index;
    for (const item of items) {
      if (item.start <= scrollTop + 80) {
        activeIndex = item.index;
      }
    }
    prefetchAhead(activeIndex);
    onVisiblePageChange(activeIndex + 1);
  }, [onVisiblePageChange, pages.length, prefetchAhead, scrollElement, virtualizer]);

  useEffect(() => {
    let frame = 0;
    const handleScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(reportVisiblePage);
    };

    handleScroll();
    scrollElement.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scrollElement.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(frame);
    };
  }, [reportVisiblePage, scrollElement]);

  if (pages.length === 0) {
    return null;
  }

  return (
    <div
      className="relative mx-auto w-full max-w-3xl"
      style={{ height: `${virtualizer.getTotalSize()}px` }}
    >
      {virtualItems.map((virtualItem) => {
        const page = pages[virtualItem.index];
        if (!page) return null;

        return (
          <div
            key={virtualItem.key}
            data-index={virtualItem.index}
            ref={virtualizer.measureElement}
            className="absolute left-0 top-0 w-full"
            style={{ transform: `translateY(${virtualItem.start}px)` }}
          >
            <VirtualPageRow
              page={page}
              pageNumber={virtualItem.index + 1}
              chapterTitle={chapterTitle}
              zoom={zoom}
              pageGap={pageGap}
              priority={virtualItem.index < 2}
              onImageLoad={() => {
                const element = document.querySelector(
                  `[data-index="${virtualItem.index}"]`,
                );
                if (element instanceof HTMLElement) {
                  virtualizer.measureElement(element);
                  recordMeasuredHeight(page.id, element.offsetHeight);
                }
                if (virtualItem.index === 0) {
                  notifyReady();
                }
                reportVisiblePage();
              }}
            />
          </div>
        );
      })}
    </div>
  );
}
