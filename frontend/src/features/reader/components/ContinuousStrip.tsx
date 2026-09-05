"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { subscribeStorageScope } from "@/lib/scoped-storage";
import { readerDebug } from "../debug";
import { continuousPageSizing } from "../fit";
import {
  DEFAULT_CONTAINER_WIDTH,
  estimatePageHeight,
  exactPageHeight,
  pageContentWidth,
  resolveContainerWidth,
} from "../page-layout";
import {
  EMPTY_HEIGHT_SAMPLES,
  estimateFromSamples,
  recordHeight,
  type HeightSamples,
} from "../page-metrics";
import { naturalPageRatio, readPageRatios, writePageRatios } from "../page-ratios";
import { pageImageUrlForBox } from "../page-url";
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
  shouldPersistFrozenHeights,
  stripPositionAt,
  type StripChapter,
  type StripPosition,
  type StripRow,
} from "../strip";
import type { ReaderPage } from "../types";
import { PageImage, type PageFrame } from "./PageImage";

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

/**
 * The divider's exact rendered height, fixed rather than measured.
 *
 * Every other row's height is discovered; this one is declared, so the strip's
 * estimate for an off-screen divider is never wrong and a seam far below the
 * reader can never shift the page under them by a few pixels as it scrolls in.
 */
const DIVIDER_HEIGHT_PX = 92;

/**
 * How far below the viewport top a row must start to count as "being read".
 *
 * Exported because a bookmark's position has to be measured against the same
 * line the page number is chosen by: capture the fraction at the viewport top
 * while `visiblePage` is chosen 80px down, and a bookmark taken just after a
 * page boundary records "0% of page 9" while the reader is looking at the
 * bottom of page 8.
 */
export const READING_LINE_PX = 80;

/** Page URLs remembered as already warmed, before the set is simply dropped. */
const PREFETCH_MEMORY_LIMIT = 2000;

const EMPTY_RELEASED: ReadonlySet<string> = new Set<string>();

/** The strip's imperative surface, handed to the reader that owns the chrome. */
export interface StripHandle {
  /**
   * Put a chapter's page at the top of the viewport, optionally `offset` px
   * further in — which is how a resumed position lands exactly where it was
   * left rather than at the top of the page it was inside.
   */
  scrollToPosition(chapterKey: string, pageNumber: number, offset?: number): void;
  /** Where a page begins, in strip coordinates. */
  pageStart(chapterKey: string, pageNumber: number): number | null;
  /**
   * Where a page begins AND ends, in strip coordinates.
   *
   * `pageStart` alone cannot answer "how far into this page am I", and a
   * caller cannot derive the height from the next page's start: the next row
   * is a divider at a chapter boundary, and there is no next row at all at the
   * end of the strip. The virtualizer has measured both edges, so it says so.
   */
  pageExtent(chapterKey: string, pageNumber: number): { start: number; end: number } | null;
  /** Where a chapter starts and ends in strip coordinates, for its progress. */
  chapterRange(chapterKey: string): { start: number; end: number } | null;
}

interface VirtualPageRowProps {
  /** This row's strip key — what every measurement of it is filed under. */
  rowKey: string;
  page: ReaderPage;
  /** The page URL resolved for the box this row paints into (`page-url.ts`). */
  imageUrl: string;
  chapterKey: string;
  pageNumber: number;
  chapterTitle: string;
  zoom: number;
  priority: boolean;
  pageGap: boolean;
  /**
   * Takes the row's identity instead of closing over it, so the strip can hand
   * every row the SAME function. A closure rebuilt per render defeats this
   * `memo` and `PageImage`'s below it, which during a fast flick is the
   * difference between a scroll frame re-rendering nothing and re-rendering
   * every visible page.
   */
  onImageLoad: (
    rowKey: string,
    chapterKey: string,
    pageNumber: number,
    natural: PageFrame | null,
  ) => void;
}

const VirtualPageRow = memo(function VirtualPageRow({
  rowKey,
  page,
  imageUrl,
  chapterKey,
  pageNumber,
  chapterTitle,
  zoom,
  priority,
  pageGap,
  onImageLoad,
}: VirtualPageRowProps) {
  const sizing = continuousPageSizing(zoom);
  // Every input is stable, so `PageImage` keeps the identity it needs to bail.
  const handleLoad = useCallback(
    (natural: PageFrame | null) => onImageLoad(rowKey, chapterKey, pageNumber, natural),
    [onImageLoad, rowKey, chapterKey, pageNumber],
  );
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
        imageUrl={imageUrl}
        alt={`${chapterTitle} page ${pageNumber}`}
        width={page.width}
        height={page.height}
        priority={priority}
        seamless={!pageGap}
        onLoad={handleLoad}
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
 *
 * Memoised because the chrome above it holds one integer of scroll progress
 * that moves on every frame of a flick. The virtualizer re-renders this itself
 * whenever the visible range moves — that is the render the strip is for — and
 * a percentage read-out has no business adding a second one to the same frame.
 */
export const ContinuousStrip = memo(function ContinuousStrip({
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
  // Per-page aspect ratios, by chapter: what the browser learned on decode plus
  // whatever a previous read left in storage. Layout-INDEPENDENT, unlike every
  // other map here, which is why the resize handler below wipes the heights and
  // leaves these alone — after a resize, every page seen once still reserves its
  // real extent immediately.
  const ratiosRef = useRef<Map<string, (number | null)[]>>(new Map());
  const dirtyChaptersRef = useRef<Set<string>>(new Set());
  // Chapters at least one of whose pages has actually decoded on screen. A
  // chapter that has not is one whose heights are all guesses (see
  // `shouldPersistFrozenHeights`), which Read-all produces on every window.
  const renderedChaptersRef = useRef<Set<string>>(new Set());
  const layoutKeyRef = useRef<string | null>(null);
  const firstChapterKeyRef = useRef<string | null>(null);
  const onPositionChangeRef = useRef(onPositionChange);

  useEffect(() => {
    onPositionChangeRef.current = onPositionChange;
  }, [onPositionChange]);

  // Layout inputs the image-load handler needs but must not DEPEND on: it is
  // handed to every visible row, and a new identity for it re-renders each one.
  const containerWidthRef = useRef(containerWidth);
  containerWidthRef.current = containerWidth;
  const zoomRef = useRef(zoom);
  zoomRef.current = zoom;
  const pageGapRef = useRef(pageGap);
  pageGapRef.current = pageGap;

  const releasedHeight = useCallback(
    (chapterKey: string) => releasedHeightsRef.current.get(chapterKey) ?? 0,
    [],
  );

  /** This chapter's remembered shapes, read from storage at most once. */
  const chapterRatios = useCallback((chapterKey: string): (number | null)[] => {
    const held = ratiosRef.current.get(chapterKey);
    if (held) return held;
    const loaded = readPageRatios(chapterKey);
    ratiosRef.current.set(chapterKey, loaded);
    return loaded;
  }, []);

  const rememberedRatio = useCallback(
    (chapterKey: string, pageNumber: number): number | null =>
      chapterRatios(chapterKey)[pageNumber - 1] ?? null,
    [chapterRatios],
  );

  // Remembered shapes belong to a profile, and the cache above is keyed only by
  // chapter. A switch has to drop it unflushed, or the arriving profile reads
  // the departing one's measurements — and writes them back under its own key.
  useEffect(
    () =>
      subscribeStorageScope(() => {
        dirtyChaptersRef.current.clear();
        ratiosRef.current.clear();
      }),
    [],
  );

  /** Flush every chapter measured since the last flush. Best-effort by design. */
  const flushRatios = useCallback(() => {
    for (const chapterKey of dirtyChaptersRef.current) {
      const ratios = ratiosRef.current.get(chapterKey);
      if (ratios) writePageRatios(chapterKey, ratios);
    }
    dirtyChaptersRef.current.clear();
  }, []);

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

  /**
   * What one page will occupy, best answer first.
   *
   * The order is the whole point. A page whose SOURCE reported dimensions, or
   * one this profile has already watched decode, has an exact extent — and the
   * running average must not be allowed to overwrite a fact with a mean. Only a
   * page nobody can size yet falls through to the samples, and only a strip
   * with no samples at all falls through to the population prior.
   */
  const pageRowHeight = useCallback(
    (page: ReaderPage, chapterKey: string, pageNumber: number): number => {
      const gap = pageGap ? PAGE_GAP_PX : 0;
      const exact = exactPageHeight(page, containerWidth, zoom);
      if (exact != null) return exact + gap;
      const remembered = rememberedRatio(chapterKey, pageNumber);
      if (remembered != null) {
        return pageContentWidth(containerWidth, zoom) * remembered + gap;
      }
      return estimateFromSamples(
        heightSamplesRef.current,
        estimatePageHeight(page, containerWidth, zoom) + gap,
      );
    },
    [containerWidth, pageGap, rememberedRatio, zoom],
  );

  const rowHeight = useCallback(
    (row: StripRow): number => {
      const measured = measuredByKeyRef.current.get(row.key);
      if (measured != null) return measured;
      if (row.kind === "spacer") return row.height;
      if (row.kind === "divider") return DIVIDER_HEIGHT_PX;
      return pageRowHeight(row.page, row.chapterKey, row.pageNumber);
    },
    [pageRowHeight],
  );

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

    // `ratiosRef` deliberately survives: an aspect ratio is a property of the
    // page, not of the column it was measured in, so a resize is exactly when
    // it is most valuable.
    measuredByKeyRef.current = new Map();
    releasedHeightsRef.current = new Map();
    heightSamplesRef.current = EMPTY_HEIGHT_SAMPLES;
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
    const box = pageContentWidth(containerWidthRef.current, zoomRef.current);
    let warmed = 0;
    for (let index = activeIndex + 1; index < strip.length && warmed < PREFETCH_AHEAD; index += 1) {
      const row = strip[index];
      if (row.kind !== "page") continue;
      warmed += 1;
      // Resolved through the SAME rule the row renders with: warming the baked
      // URL and then painting a different one downloads every page twice.
      const url = pageImageUrlForBox(row.page.imageUrl, box);
      if (seen.has(url)) continue;
      seen.add(url);
      const preloader = new window.Image();
      preloader.decoding = "async";
      preloader.src = url;
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
      scrollToPosition: (chapterKey, pageNumber, offset = 0) => {
        const index = findStripRow(rowsRef.current, chapterKey, pageNumber);
        if (index < 0) return;
        if (offset > 0) {
          // Anchored to the page, so the error is that ONE page's estimate
          // rather than every page between here and the top of the strip.
          const start = rowStart(index);
          if (start != null) {
            scrollElement.scrollTop = Math.max(0, Math.round(start + offset));
            return;
          }
        }
        virtualizer.scrollToIndex(index, { align: "start" });
      },
      pageStart: (chapterKey, pageNumber) => {
        const index = findStripRow(rowsRef.current, chapterKey, pageNumber);
        return index < 0 ? null : rowStart(index);
      },
      pageExtent: (chapterKey, pageNumber) => {
        const index = findStripRow(rowsRef.current, chapterKey, pageNumber);
        if (index < 0) return null;
        // Through `rowStart` so the measurement pass runs before the cache is
        // read; a strip that just changed would otherwise answer with the
        // previous row list's geometry.
        const start = rowStart(index);
        if (start == null) return null;
        const measured = virtualizer.measurementsCache[index];
        return { start, end: measured ? measured.end : start };
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

  /** The CSS box one page paints into — what the page URL is resolved against. */
  const contentWidth = pageContentWidth(containerWidth, zoom);

  const notifyReady = useCallback(() => {
    if (readyNotifiedRef.current) return;
    readyNotifiedRef.current = true;
    onImagesReady?.();
  }, [onImagesReady]);

  /**
   * Fold a page's real rendered height into the running average that backs
   * `estimateSize`.
   *
   * Nothing is invalidated here on purpose. A drifting average used to trigger
   * `virtualizer.measure()`, which is `itemSizeCache.clear()` — EVERY row,
   * including the ones above the reader, re-derived with no scroll
   * compensation, so a run crossing from page-scan chapters into webtoon ones
   * jumped on the frame the average moved. It was never needed: a row that has
   * never been measured is not in that cache at all, so it is re-estimated from
   * these samples on the next measurement pass regardless, and this write
   * triggers one.
   */
  const recordMeasuredHeight = useCallback((key: string, height: number) => {
    if (!(height > 0)) return;
    const previous = measuredByKeyRef.current.get(key);
    if (previous != null && Math.abs(previous - height) < 1) return;
    measuredByKeyRef.current.set(key, height);
    heightSamplesRef.current = recordHeight(
      heightSamplesRef.current,
      previous,
      height,
    );
  }, []);

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

  /**
   * A page finished decoding: correct its estimated height with the real one.
   *
   * One function for the whole strip, keyed by the row rather than bound to it,
   * because the alternative — a closure per row — is what kept every visible
   * `VirtualPageRow` and `PageImage` re-rendering on renders where nothing
   * about them had changed.
   *
   * The node comes from the virtualizer's own element cache, which the
   * `measureElement` ref below already populates under this same key. Looking
   * it up by key rather than by `data-index` is also the correct lookup: a
   * prepended chapter shifts every index while no key moves.
   */
  const handleImageLoad = useCallback(
    (
      rowKey: string,
      chapterKey: string,
      pageNumber: number,
      natural: PageFrame | null,
    ) => {
      // The decoded image's own shape, remembered for this chapter so the next
      // open of it reserves exact extents from the first frame.
      const ratio = natural ? naturalPageRatio(natural.width, natural.height) : null;
      if (ratio != null) {
        const ratios = chapterRatios(chapterKey);
        if (ratios[pageNumber - 1] !== ratio) {
          ratios[pageNumber - 1] = ratio;
          dirtyChaptersRef.current.add(chapterKey);
        }
      }
      renderedChaptersRef.current.add(chapterKey);

      const element = virtualizer.elementsCache.get(rowKey);
      if (element) {
        // Derived from the intrinsic size when there is one, NOT from the row's
        // box. `setLoaded` in `PageImage` has not been committed yet at this
        // point in the event, so the row is still standing at its placeholder
        // aspect ratio — reading it back here would feed the estimate its own
        // guess and the running average would never learn anything.
        //
        // The DOM read is still the fallback for a page the browser resolved no
        // intrinsic size for, and still taken BEFORE anything is written back:
        // a write ends by correcting the scroll offset to absorb the height
        // change, and a read after it has to flush layout a second time.
        const height =
          ratio != null
            ? Math.round(
                pageContentWidth(containerWidthRef.current, zoomRef.current) * ratio,
              ) + (pageGapRef.current ? PAGE_GAP_PX : 0)
            : Math.round(element.getBoundingClientRect().height);
        if (height > 0) {
          // Handed the derived height rather than `measureElement`, which reads
          // the DOM back — the same placeholder box the note above explains is
          // a lie. Publishing that put a third, wrong number in the size cache
          // and left the ResizeObserver (already watching this node, from the
          // ref below) to correct it a frame later, so every unknown-dimension
          // page resized twice. The observer still confirms this one; it just
          // agrees with it now. `data-index` is the attribute the virtualizer
          // resolves an element's index by itself.
          const index = Number(element.getAttribute("data-index"));
          if (ratio != null && Number.isInteger(index)) {
            virtualizer.resizeItem(index, height);
          } else {
            virtualizer.measureElement(element);
          }
          recordMeasuredHeight(rowKey, height);
        }
      }
      // The first page to paint is the strip's "ready", whichever one it is: a
      // resumed chapter may never render row 0.
      notifyReady();
      reportPosition();
    },
    [chapterRatios, notifyReady, recordMeasuredHeight, reportPosition, virtualizer],
  );

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
   *
   * Two things are deliberate about WHICH chapters get frozen numbers written
   * down. A chapter re-entering the released set is re-frozen rather than left
   * on the height it had the first time — it has been read since, so its real
   * measurements are what the spacer must stand at, and its cold first guess
   * would collapse the strip above the reader. And a chapter that has never
   * been rendered keeps no per-page numbers at all: see
   * `shouldPersistFrozenHeights`.
   */
  useEffect(() => {
    if (activeChapterKey === null) return;
    const activeIndex = chapterIndexOf(chapters, activeChapterKey);
    if (activeIndex < 0) return;
    const next = releasedChapterKeys(chapters, activeIndex);
    if (next.size === released.size && [...next].every((key) => released.has(key))) {
      return;
    }

    chapters.forEach((chapter, index) => {
      // Already released and untouched since: the numbers it was frozen at are
      // still the numbers its spacer is standing on.
      if (!next.has(chapter.chapterKey) || released.has(chapter.chapterKey)) return;
      const { total, frozen } = freezeChapterHeight(
        chapter,
        measuredByKeyRef.current,
        (page, pageNumber) => pageRowHeight(page, chapter.chapterKey, pageNumber),
      );
      releasedHeightsRef.current.set(chapter.chapterKey, total);
      if (
        !shouldPersistFrozenHeights(
          index,
          activeIndex,
          renderedChaptersRef.current.has(chapter.chapterKey),
        )
      ) {
        return;
      }
      for (const [key, height] of frozen) {
        measuredByKeyRef.current.set(key, height);
      }
    });

    // A released chapter is done being measured, so its shapes are final: this
    // is the natural moment to write them down, and it keeps a Read-all session
    // from touching localStorage once per decoded page.
    flushRatios();
    readerDebug("strip-released", { released: next.size, chapters: chapters.length });
    setReleased(next);
  }, [
    activeChapterKey,
    chapters,
    containerWidth,
    flushRatios,
    pageGap,
    pageRowHeight,
    released,
    zoom,
  ]);

  // The chapter being read is never released, so without this the one chapter
  // the reader actually finished would be the one never remembered.
  useEffect(() => flushRatios, [flushRatios]);

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
                rowKey={row.key}
                page={row.page}
                imageUrl={pageImageUrlForBox(row.page.imageUrl, contentWidth)}
                chapterKey={row.chapterKey}
                pageNumber={row.pageNumber}
                chapterTitle={row.label}
                zoom={zoom}
                pageGap={pageGap}
                priority={virtualItem.index < 2}
                onImageLoad={handleImageLoad}
              />
            )}
          </div>
        );
      })}
    </div>
  );
});
