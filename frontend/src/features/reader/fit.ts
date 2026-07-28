import type { FitMode, ReadingMode } from "./types";

export const MIN_ZOOM = 0.5;
export const MAX_ZOOM = 3;
export const ZOOM_STEP = 0.1;

/** width / height of the placeholder box for a page that reports no dimensions. */
const DEFAULT_PAGE_ASPECT = 2 / 3;

export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return 1;
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(zoom.toFixed(2))));
}

/** Step the zoom by whole notches; negative steps zoom out. */
export function zoomBy(zoom: number, steps: number): number {
  return clampZoom(zoom + steps * ZOOM_STEP);
}

/**
 * The wheel interaction contract, in one place so the paged and continuous
 * views cannot drift: ctrl/⌘+wheel zooms, a plain wheel is left alone so it
 * still scrolls. Returns the number of zoom notches, or 0 to ignore the event.
 */
export function wheelZoomSteps(event: {
  deltaY: number;
  ctrlKey: boolean;
  metaKey: boolean;
}): number {
  if (!event.ctrlKey && !event.metaKey) return 0;
  if (!Number.isFinite(event.deltaY) || event.deltaY === 0) return 0;
  return event.deltaY < 0 ? 1 : -1;
}

export function pageAspect(width?: number | null, height?: number | null): number {
  if (width != null && height != null && width > 0 && height > 0) {
    return width / height;
  }
  return DEFAULT_PAGE_ASPECT;
}

/**
 * A long strip has no single page height to fit against — every page is a
 * different length and the virtualizer sizes them from the container width —
 * so fit-height degrades to fit-width while scrolling continuously.
 */
export function effectiveFitMode(fitMode: FitMode, mode: ReadingMode): FitMode {
  return mode === "continuous" ? "width" : fitMode;
}

export interface PageFitInput {
  containerWidth: number;
  containerHeight: number;
  pageWidth?: number | null;
  pageHeight?: number | null;
  fitMode: FitMode;
  zoom: number;
  /** Pages shown side by side (2 for a double-page spread). */
  slots?: number;
  /** Gutter between slots, in CSS pixels. */
  gap?: number;
}

export interface PageFitResult {
  width: number;
  height: number;
}

/**
 * The rendered box for one page. Both dimensions are returned so the paged view
 * can reserve the exact space before the image decodes, which keeps a page turn
 * from reflowing under the reader.
 */
export function resolvePageFit(input: PageFitInput): PageFitResult {
  const slots = Math.max(1, Math.floor(input.slots ?? 1));
  const gap = Math.max(0, input.gap ?? 0);
  const containerWidth = Math.max(0, input.containerWidth);
  const containerHeight = Math.max(0, input.containerHeight);
  const availableWidth = Math.max(0, (containerWidth - gap * (slots - 1)) / slots);
  const aspect = pageAspect(input.pageWidth, input.pageHeight);
  const zoom = clampZoom(input.zoom);

  if (input.fitMode === "height") {
    const height = containerHeight * zoom;
    return { width: height * aspect, height };
  }

  if (input.fitMode === "original") {
    const intrinsic =
      input.pageWidth != null && input.pageWidth > 0 ? input.pageWidth : availableWidth;
    const width = intrinsic * zoom;
    return { width, height: width / aspect };
  }

  const width = availableWidth * zoom;
  return { width, height: width / aspect };
}

export interface ContinuousPageSizing {
  width: string;
  maxWidth: string;
}

/**
 * Width of a page in the continuous strip. Kept as CSS strings because the
 * strip is fluid: it tracks the container rather than a measured pixel box.
 */
export function continuousPageSizing(zoom: number): ContinuousPageSizing {
  const safeZoom = clampZoom(zoom);
  return {
    width: safeZoom === 1 ? "100%" : `${safeZoom * 100}%`,
    maxWidth: safeZoom <= 1 ? "48rem" : "none",
  };
}
