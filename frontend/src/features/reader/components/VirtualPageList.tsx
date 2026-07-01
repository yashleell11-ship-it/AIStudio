"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { readerDebug } from "../debug";
import type { ReaderPage } from "../types";
import {
  DEFAULT_CONTAINER_WIDTH,
  estimatePageHeight,
  resolveContainerWidth,
} from "../page-layout";
import { restoreChapterScroll } from "../scroll-preparation";
import { PageImage } from "./PageImage";

interface VirtualPageRowProps {
  page: ReaderPage;
  pageNumber: number;
  chapterTitle: string;
  zoom: number;
  priority: boolean;
  onImageLoad: () => void;
}

const VirtualPageRow = memo(function VirtualPageRow({
  page,
  pageNumber,
  chapterTitle,
  zoom,
  priority,
  onImageLoad,
}: VirtualPageRowProps) {
  return (
    <div
      id={`reader-page-${pageNumber}`}
      data-page={pageNumber}
      className="mx-auto w-full pb-1"
      style={{
        width: zoom === 1 ? "100%" : `${zoom * 100}%`,
        maxWidth: zoom <= 1 ? "48rem" : "none",
      }}
    >
      <PageImage
        imageUrl={page.imageUrl}
        alt={`${chapterTitle} page ${pageNumber}`}
        width={page.width}
        height={page.height}
        priority={priority}
        onLoad={onImageLoad}
      />
    </div>
  );
});

interface VirtualPageListProps {
  pages: ReaderPage[];
  chapterTitle: string;
  zoom: number;
  scrollElement: HTMLElement;
  initialScrollTop: number;
  onVisiblePageChange: (pageNumber: number) => void;
  onImagesReady?: () => void;
}

export function VirtualPageList({
  pages,
  chapterTitle,
  zoom,
  scrollElement,
  initialScrollTop,
  onVisiblePageChange,
  onImagesReady,
}: VirtualPageListProps) {
  const [containerWidth, setContainerWidth] = useState(DEFAULT_CONTAINER_WIDTH);
  const readyNotifiedRef = useRef(false);
  const initialRestorePendingRef = useRef(initialScrollTop > 0);

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
  }, [initialScrollTop, pages]);

  useEffect(() => {
    readerDebug("virtual-page-list-mounted", {
      pagesLength: pages.length,
      scrollReady: true,
      containerWidth,
      measuredWidth: scrollElement.clientWidth,
    });
  }, [containerWidth, pages.length, scrollElement]);

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
    onVisiblePageChange(activeIndex + 1);
  }, [onVisiblePageChange, pages.length, scrollElement, virtualizer]);

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
