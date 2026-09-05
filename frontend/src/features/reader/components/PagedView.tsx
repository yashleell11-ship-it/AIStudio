"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { resolvePageFit, wheelZoomSteps } from "../fit";
import { pageImageUrlForBox } from "../page-url";
import { resolveTapZone, type TapZone, type TapZoneConfig } from "../keymap";
import { PRELOAD_AHEAD_PAGED } from "../preload";
import { spreadDisplayOrder } from "../spread";
import type { FitMode, ReaderPage, ReadingDirection } from "../types";
import { PageImage } from "./PageImage";

/** Gutter between the two halves of a spread, in CSS pixels. */
const SPREAD_GAP = 8;

/**
 * Pages warmed past the current view. A paged mode holds only the visible pages
 * in the DOM, so without this every turn starts from a cold image.
 */
const PREFETCH_AHEAD = PRELOAD_AHEAD_PAGED;

interface PagedViewProps {
  pages: ReaderPage[];
  chapterTitle: string;
  /** Page numbers on screen, in reading order. */
  view: number[];
  /**
   * Page slots the viewport is divided into — 2 in double-page mode even when
   * the view holds a single page. A lone cover must occupy the same half-width
   * slot it would in a spread, or the page size lurches on the first turn.
   */
  slotsPerView: number;
  direction: ReadingDirection;
  fitMode: FitMode;
  zoom: number;
  /** Resolved left/centre/right tap behaviour — see `keymap.ts`. RTL-aware
   * already baked in by the caller (`defaultTapZoneConfig`/`ChapterReader`). */
  tapZoneConfig: TapZoneConfig;
  onTap: (zone: TapZone) => void;
  onZoom: (steps: number) => void;
  /** Subtle fade between page turns (reader settings, off by default). */
  pageTransition?: boolean;
}

export function PagedView({
  pages,
  chapterTitle,
  view,
  slotsPerView,
  direction,
  fitMode,
  zoom,
  tapZoneConfig,
  onTap,
  onZoom,
  pageTransition = false,
}: PagedViewProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const onZoomRef = useRef(onZoom);

  useEffect(() => {
    onZoomRef.current = onZoom;
  }, [onZoom]);

  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const measure = () => {
      setSize({ width: stage.clientWidth, height: stage.clientHeight });
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(stage);
    return () => observer.disconnect();
  }, []);

  // Zoom needs a non-passive listener so ctrl+wheel can cancel the browser's own
  // page zoom; React's onWheel is registered passively and cannot.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const handleWheel = (event: WheelEvent) => {
      const steps = wheelZoomSteps(event);
      if (steps === 0) return;
      event.preventDefault();
      onZoomRef.current(steps);
    };

    stage.addEventListener("wheel", handleWheel, { passive: false });
    return () => stage.removeEventListener("wheel", handleWheel);
  }, []);

  const warmedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (typeof window === "undefined" || view.length === 0) return;
    const lastIndex = Math.max(...view) - 1;
    for (let offset = 1; offset <= PREFETCH_AHEAD; offset += 1) {
      const next = pages[lastIndex + offset];
      if (!next) continue;
      // Warmed at the width it will be PAINTED at. A paged fit routinely
      // resolves wider than the reader column the URL was baked for — fit
      // height, fit original, or simply a wide stage — and warming the baked
      // URL there downloads every page once to throw it away.
      const url = pageImageUrlForBox(
        next.imageUrl,
        resolvePageFit({
          containerWidth: size.width,
          containerHeight: size.height,
          pageWidth: next.width,
          pageHeight: next.height,
          fitMode,
          zoom,
          slots: Math.max(1, slotsPerView),
          gap: SPREAD_GAP,
        }).width,
      );
      if (warmedRef.current.has(url)) continue;
      warmedRef.current.add(url);
      const preloader = new window.Image();
      preloader.decoding = "async";
      preloader.src = url;
    }
  }, [fitMode, pages, size.height, size.width, slotsPerView, view, zoom]);

  const handleClick = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      const rect = event.currentTarget.getBoundingClientRect();
      onTap(resolveTapZone(event.clientX, rect, tapZoneConfig));
    },
    [onTap, tapZoneConfig],
  );

  const displayOrder = spreadDisplayOrder(view, direction);
  const slots = Math.max(1, slotsPerView);

  return (
    // `m-auto` on the child rather than `items-center` on the parent: a centred
    // flex container clips overflow past its start edge, which would put the top
    // of a zoomed page permanently out of reach.
    <div
      ref={stageRef}
      className="flex min-h-0 flex-1 overflow-auto"
      role="presentation"
      onClick={handleClick}
    >
      <div
        // Re-keying on the view forces React to remount this wrapper on every
        // turn, which is what restarts the fade animation below — a CSS-only
        // "enter" transition needs a fresh element, not a class toggle on a
        // persistent one.
        key={pageTransition ? view.join("-") : undefined}
        className={cn(
          "m-auto flex items-center justify-center",
          pageTransition && "reader-page-transition-enter",
        )}
        style={{ gap: `${SPREAD_GAP}px` }}
      >
        {displayOrder.map((pageNumber) => {
          const page = pages[pageNumber - 1];
          if (!page) return null;

          const frame = resolvePageFit({
            containerWidth: size.width,
            containerHeight: size.height,
            pageWidth: page.width,
            pageHeight: page.height,
            fitMode,
            zoom,
            slots,
            gap: SPREAD_GAP,
          });

          return (
            <PageImage
              key={page.id}
              imageUrl={pageImageUrlForBox(page.imageUrl, frame.width)}
              alt={`${chapterTitle} page ${pageNumber}`}
              width={page.width}
              height={page.height}
              frame={frame}
              seamless
            />
          );
        })}
      </div>
    </div>
  );
}
