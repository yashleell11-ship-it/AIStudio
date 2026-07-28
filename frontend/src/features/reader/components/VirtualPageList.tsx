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
import { restoreChapterScroll } from "../scroll-preparation";
import { PageImage } from "./PageImage";

/** Number of upcoming pages to warm into the browser cache ahead of the reader. */
const PREFETCH_AHEAD = 2;

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
    estimateSize: (index) =>
      estimatePageHeight(pages[index], containerWidth, zoom),
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
