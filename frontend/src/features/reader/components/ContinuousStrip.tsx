"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { readerDebug } from "../debug";
import { continuousPageSizing } from "../fit";
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
import {
  buildStripRows,
  chapterFirstPageRow,
  chapterIndexOf,
  chapterLastRow,
  findStripRow,
  freezeChapterHeight,
  releasedChapterKeys,
  stripPositionAt,
  type StripChapter,
  type StripPosition,
  type StripRow,
} from "../strip";
import type { ReaderPage } from "../types";
import { PageImage } from "./PageImage";

/**
 * Upcoming pages warmed into the browser cache ahead of the reader. Counted in
 * ROWS across the whole strip, so warming naturally spills over a chapter
 * boundary — which is the entire point of a continuous strip: the first images
 * of the next chapter are already decoding while the last of this one is on
 * screen (spec R1, "prefetch before the reader reaches the seam").
 */
const PREFETCH_AHEAD = PRELOAD_AHEAD_CONTINUOUS;

/** The thin separator height (`pb-2` = 0.5rem) when the page-gap setting is on. */
const PAGE_GAP_PX = 8;

/** Re-measure the virtualizer when the running average shifts more than this. */
const ESTIMATE_DRIFT_RATIO = 0.12;

/**
 * The divider's exact rendered height, fixed rather than measured.
 *
 * Every other row's height is discovered; this one is declared, so the strip's
 * estimate for an off-screen divider is never wrong and a seam far below the
 * reader can never shift the page under them by a few pixels as it scrolls in.
 */
const DIVIDER_HEIGHT_PX = 92;

/** How far below the viewport top a row must start to count as "being read". */
const READING_LINE_PX = 80;

/** Page URLs remembered as already warmed, before the set is simply dropped. */
const PREFETCH_MEMORY_LIMIT = 2000;

const EMPTY_RELEASED: ReadonlySet<string> = new Set<string>();

/** The strip's imperative surface, handed to the reader that owns the chrome. */
export interface StripHandle {
  /** Put a chapter's page at the top of the viewport. */
  scrollToPosition(chapterKey: string, pageNumber: number): void;
  /** Where a chapter starts and ends in strip coordinates, for its progress. */
  chapterRange(chapterKey: string): { start: number; end: number } | null;
}

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

/**
 * The seam marker.
 *
 * A hairline, the chapter's name, and nothing else: it has to be findable when
 * looked for and invisible when read past. Deliberately not a button and not a
 * card — the boundary is no longer a decision point, it is just a place in the
 * scroll, and anything clickable there would invite a stop.
 */
const ChapterDivider = memo(function ChapterDivider({ label }: { label: string }) {
  return (
    <div
      className="mx-auto flex w-full max-w-3xl items-center gap-4 px-6"
      style={{ height: `${DIVIDER_HEIGHT_PX}px` }}
    >
      <span className="h-px flex-1 bg-border/70" aria-hidden />
      <span className="whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.22em] text-muted">
        {label}
      </span>
      <span className="h-px flex-1 bg-border/70" aria-hidden />
    </div>
  );
});

interface ContinuousStripProps {
  /** Loaded chapters, in reading order. The strip renders them as one scroll. */
  chapters: readonly StripChapter[];
  zoom: number;
  pageGap: boolean;
  scrollElement: HTMLElement;
  initialScrollTop: number;
  /** Where the reader is, reported on every scroll frame. */
  onPositionChange: (position: StripPosition) => void;
  onImagesReady?: () => void;
  /**
   * Hands the parent the strip's imperative surface. The scrubber must land on
   * the page it points at and the chrome must know where the current chapter
   * begins, and only the virtualizer has the measured heights those need.
   */
  onHandleReady?: (handle: StripHandle | null) => void;
}

/**
 * Several chapters, one scroll (spec 2026-09-05 R1/R2).
 *
 * The reader used to mount one chapter's pages and swap the lot at the
 * boundary. This renders the flattened row list from `strip.ts` instead, so the
 * end of chapter N and the start of N+1 are ordinary neighbouring rows and
 * crossing the seam — in either direction — is just scrolling.
 *
 * Two invariants make that safe at series scale:
 *
 * 1. **Row keys are stable.** A page's key is `chapterKey:pageNumber`, so
 *    prepending a chapter shifts every index but no key: the virtualizer keeps
 *    its measurements, and so does the height map below.
 * 2. **Releasing preserves height.** A chapter outside the render radius has
 *    its pages replaced by ONE spacer of exactly the height they occupied
 *    (frozen page by page first, so re-expanding restores the same total).
 *    Hundreds of chapters therefore cost hundreds of rows, not tens of
 *    thousands, and nothing under the reader ever moves.
 */
export function ContinuousStrip({
  chapters,
  zoom,
  pageGap,
  scrollElement,
  initialScrollTop,
  onPositionChange,
  onImagesReady,
  onHandleReady,
}: ContinuousStripProps) {
  const [containerWidth, setContainerWidth] = useState(DEFAULT_CONTAINER_WIDTH);
  const [released, setReleased] = useState<ReadonlySet<string>>(EMPTY_RELEASED);
  const [activeChapterKey, setActiveChapterKey] = useState<string | null>(null);

  const readyNotifiedRef = useRef(false);
  const initialRestorePendingRef = useRef(initialScrollTop > 0);
  const prefetchedRef = useRef<Set<string>>(new Set());
  // Measured row heights, keyed the way rows are keyed, so they survive an
  // index shift. Also the source of truth for a released chapter's height.
  const measuredByKeyRef = useRef<Map<string, number>>(new Map());
  const releasedHeightsRef = useRef<Map<string, number>>(new Map());
  const heightSamplesRef = useRef<HeightSamples>(EMPTY_HEIGHT_SAMPLES);
  const lastAvgEstimateRef = useRef(0);
  const layoutKeyRef = useRef<string | null>(null);
  const firstChapterKeyRef = useRef<string | null>(null);
  const onPositionChangeRef = useRef(onPositionChange);

  useEffect(() => {
    onPositionChangeRef.current = onPositionChange;
  }, [onPositionChange]);

  const releasedHeight = useCallback(
    (chapterKey: string) => releasedHeightsRef.current.get(chapterKey) ?? 0,
    [],
  );

  const rows = useMemo(
    () => buildStripRows(chapters, { released, releasedHeight }),
    [chapters, released, releasedHeight],
  );
  const rowsRef = useRef<StripRow[]>(rows);
  rowsRef.current = rows;

  useLayoutEffect(() => {
    const measure = () => {
      setContainerWidth(resolveContainerWidth(scrollElement));
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(scrollElement);
    return () => observer.disconnect();
  }, [scrollElement]);

  const rowHeight = useCallback(
    (row: StripRow): number => {
      const measured = measuredByKeyRef.current.get(row.key);
      if (measured != null) return measured;
      if (row.kind === "spacer") return row.height;
      if (row.kind === "divider") return DIVIDER_HEIGHT_PX;
      const fallback =
        estimatePageHeight(row.page, containerWidth, zoom) + (pageGap ? PAGE_GAP_PX : 0);
      return estimateFromSamples(heightSamplesRef.current, fallback);
    },
    [containerWidth, pageGap, zoom],
  );

  // TanStack Virtual returns fresh functions each render that cannot be memoized.
  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollElement,
    estimateSize: (index) => {
      const row = rowsRef.current[index];
      if (!row) return estimateFromSamples(heightSamplesRef.current, 0);
      return rowHeight(row);
    },
    overscan: 4,
    getItemKey: (index) => rowsRef.current[index]?.key ?? index,
  });

  const virtualItems = virtualizer.getVirtualItems();

  /** A row's exact start offset, once the measurements are up to date. */
  const rowStart = useCallback(
    (index: number): number | null => {
      if (index < 0) return null;
      // Forces `getMeasurements()` to run for the current row list before the
      // cache below is read; without it a just-changed strip answers stale.
      virtualizer.getTotalSize();
      return virtualizer.measurementsCache[index]?.start ?? null;
    },
    [virtualizer],
  );

  /**
   * Keep the reader's place when a chapter is prepended.
   *
   * Everything already in the strip moves down by the height inserted above it.
   * That height is exactly where the old first chapter now starts, so adding it
   * to the scroll offset leaves the page under the reader untouched. Later
   * corrections — the inserted pages measuring taller or shorter than their
   * estimate — are the virtualizer's own above-viewport adjustment, not ours.
   */
  useLayoutEffect(() => {
    const nextFirst = chapters[0]?.chapterKey ?? null;
    const previousFirst = firstChapterKeyRef.current;
    firstChapterKeyRef.current = nextFirst;
    if (previousFirst === null || nextFirst === null) return;
    if (previousFirst === nextFirst) return;

    const anchorRow = chapterFirstPageRow(rows, previousFirst);
    if (anchorRow <= 0) return;
    const start = rowStart(anchorRow);
    if (start == null || start <= 0) return;
    scrollElement.scrollTop += start;
    readerDebug("strip-prepended", { chapter: nextFirst, shift: start });
    // `rowStart` closes over the virtualizer, whose identity changes each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chapters, rows, scrollElement]);

  /**
   * Measured heights are relative to the column width and the zoom level. When
   * either moves, every stored height is a lie — including the frozen ones a
   * released chapter stands on — so the whole picture is rebuilt from scratch
   * and every chapter is expanded again rather than left standing at a height
   * that no longer exists.
   */
  useLayoutEffect(() => {
    const layoutKey = `${Math.round(containerWidth)}:${zoom}`;
    const previous = layoutKeyRef.current;
    layoutKeyRef.current = layoutKey;
    if (previous === null || previous === layoutKey) return;

    measuredByKeyRef.current = new Map();
    releasedHeightsRef.current = new Map();
    heightSamplesRef.current = EMPTY_HEIGHT_SAMPLES;
    lastAvgEstimateRef.current = 0;
    setReleased(EMPTY_RELEASED);
    virtualizer.measure();
    // `virtualizer` identity churns per render; this must run on layout change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerWidth, zoom]);

  const prefetchAhead = useCallback((activeIndex: number) => {
    if (typeof window === "undefined") return;
    const seen = prefetchedRef.current;
    // A Read-all session crosses thousands of pages; the set is a leak
    // otherwise, and re-warming an already-cached URL costs nothing.
    if (seen.size > PREFETCH_MEMORY_LIMIT) seen.clear();
    const strip = rowsRef.current;
    let warmed = 0;
    for (let index = activeIndex + 1; index < strip.length && warmed < PREFETCH_AHEAD; index += 1) {
      const row = strip[index];
      if (row.kind !== "page") continue;
      warmed += 1;
      if (seen.has(row.page.imageUrl)) continue;
      seen.add(row.page.imageUrl);
      const preloader = new window.Image();
      preloader.decoding = "async";
      preloader.src = row.page.imageUrl;
    }
  }, []);

  useEffect(() => {
    readerDebug("continuous-strip-mounted", {
      chapters: chapters.length,
      rows: rows.length,
      containerWidth,
      measuredWidth: scrollElement.clientWidth,
    });
    // Mount log only — re-firing it on every row change would be noise.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useLayoutEffect(() => {
    if (rows.length === 0) return;
    if (!initialRestorePendingRef.current || initialScrollTop <= 0) return;
    virtualizer.measure();
    if (scrollElement.scrollTop !== initialScrollTop) {
      restoreChapterScroll(scrollElement, initialScrollTop);
    }
    if (scrollElement.scrollTop === initialScrollTop) {
      initialRestorePendingRef.current = false;
    }
    // virtualizer identity changes each render; remeasure when inputs change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerWidth, initialScrollTop, rows.length, scrollElement, zoom]);

  // No dependency array on purpose: the virtualizer is re-read every render so
  // the published handle always closes over current measurements.
  useEffect(() => {
    if (!onHandleReady) return;
    onHandleReady({
      scrollToPosition: (chapterKey, pageNumber) => {
        const index = findStripRow(rowsRef.current, chapterKey, pageNumber);
        if (index < 0) return;
        virtualizer.scrollToIndex(index, { align: "start" });
      },
      chapterRange: (chapterKey) => {
        const strip = rowsRef.current;
        const firstRow = chapterFirstPageRow(strip, chapterKey);
        const anchor = firstRow >= 0 ? firstRow : findStripRow(strip, chapterKey, 1);
        if (anchor < 0) return null;
        const lastRow = chapterLastRow(strip, chapterKey);
        const start = rowStart(anchor);
        if (start == null) return null;
        const last = virtualizer.measurementsCache[lastRow];
        return { start, end: last ? last.end : start };
      },
    });
    return () => onHandleReady(null);
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

  const reportPosition = useCallback(() => {
    const strip = rowsRef.current;
    if (strip.length === 0) return;
    const items = virtualizer.getVirtualItems();
    if (items.length === 0) return;

    const scrollTop = scrollElement.scrollTop;
    let activeIndex = items[0].index;
    for (const item of items) {
      if (item.start <= scrollTop + READING_LINE_PX) {
        activeIndex = item.index;
      }
    }
    prefetchAhead(activeIndex);

    const position = stripPositionAt(strip, activeIndex);
    if (!position) return;
    setActiveChapterKey(position.chapterKey);
    onPositionChangeRef.current(position);
  }, [prefetchAhead, scrollElement, virtualizer]);

  useEffect(() => {
    let frame = 0;
    const handleScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(reportPosition);
    };

    handleScroll();
    scrollElement.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      scrollElement.removeEventListener("scroll", handleScroll);
      cancelAnimationFrame(frame);
    };
  }, [reportPosition, scrollElement]);

  /**
   * Release the chapters the reader has left behind (or not yet reached).
   *
   * Each one's page heights are frozen into the height map first, so the spacer
   * that replaces them is exactly as tall as they were and expanding it again
   * puts every page back where it was. That is what lets a Read-all session
   * cross a hundred chapters without the strip ever lurching.
   */
  useEffect(() => {
    if (activeChapterKey === null) return;
    const activeIndex = chapterIndexOf(chapters, activeChapterKey);
    if (activeIndex < 0) return;
    const next = releasedChapterKeys(chapters, activeIndex);
    if (next.size === released.size && [...next].every((key) => released.has(key))) {
      return;
    }

    for (const chapter of chapters) {
      if (!next.has(chapter.chapterKey) || releasedHeightsRef.current.has(chapter.chapterKey)) {
        continue;
      }
      const { total, frozen } = freezeChapterHeight(
        chapter,
        measuredByKeyRef.current,
        (page) =>
          estimateFromSamples(
            heightSamplesRef.current,
            estimatePageHeight(page, containerWidth, zoom) + (pageGap ? PAGE_GAP_PX : 0),
          ),
      );
      for (const [key, height] of frozen) {
        measuredByKeyRef.current.set(key, height);
      }
      releasedHeightsRef.current.set(chapter.chapterKey, total);
    }

    readerDebug("strip-released", { released: next.size, chapters: chapters.length });
    setReleased(next);
  }, [activeChapterKey, chapters, containerWidth, pageGap, released, zoom]);

  if (rows.length === 0) {
    return null;
  }

  return (
    <div
      className="relative mx-auto w-full max-w-3xl"
      style={{ height: `${virtualizer.getTotalSize()}px` }}
    >
      {virtualItems.map((virtualItem) => {
        const row = rows[virtualItem.index];
        if (!row) return null;

        return (
          <div
            key={virtualItem.key}
            data-index={virtualItem.index}
            ref={virtualizer.measureElement}
            className="absolute left-0 top-0 w-full"
            style={{ transform: `translateY(${virtualItem.start}px)` }}
          >
            {row.kind === "divider" ? (
              <ChapterDivider label={row.label} />
            ) : row.kind === "spacer" ? (
              <div style={{ height: `${row.height}px` }} aria-hidden />
            ) : (
              <VirtualPageRow
                page={row.page}
                pageNumber={row.pageNumber}
                chapterTitle={row.label}
                zoom={zoom}
                pageGap={pageGap}
                priority={virtualItem.index < 2}
                onImageLoad={() => {
                  const element = document.querySelector(
                    `[data-index="${virtualItem.index}"]`,
                  );
                  if (element instanceof HTMLElement) {
                    virtualizer.measureElement(element);
                    recordMeasuredHeight(row.key, element.offsetHeight);
                  }
                  // The first page to paint is the strip's "ready", whichever
                  // one it is: a resumed chapter may never render row 0.
                  notifyReady();
                  reportPosition();
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
