import type { ReadingDirection } from "./types";

/**
 * Scrubber geometry. The handle sits at 0 on the first page and at 1 on the
 * last, so both ends of a chapter are reachable by dragging to the rail — a bar
 * that maps page N to N/total can never reach the final page.
 */
export function scrubRatioForPage(page: number, pageCount: number): number {
  if (!Number.isFinite(pageCount) || pageCount <= 1) return 1;
  const clamped = Math.min(pageCount, Math.max(1, Math.round(page)));
  return (clamped - 1) / (pageCount - 1);
}

export function scrubPercent(page: number, pageCount: number): number {
  return scrubRatioForPage(page, pageCount) * 100;
}

export function pageFromScrubRatio(ratio: number, pageCount: number): number {
  if (!Number.isFinite(pageCount) || pageCount <= 0) return 1;
  if (!Number.isFinite(ratio)) return 1;
  const clampedRatio = Math.min(1, Math.max(0, ratio));
  const page = Math.round(clampedRatio * (Math.floor(pageCount) - 1)) + 1;
  return Math.min(Math.floor(pageCount), Math.max(1, page));
}

/**
 * Pointer position → track ratio. A right-to-left chapter runs its scrubber the
 * same way it runs its pages: the start of the chapter is on the right.
 */
export function scrubRatioFromPointer(
  clientX: number,
  rect: { left: number; width: number },
  direction: ReadingDirection,
): number {
  if (!(rect.width > 0)) return 0;
  const raw = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
  return direction === "rtl" ? 1 - raw : raw;
}

export function pageFromPointer(
  clientX: number,
  rect: { left: number; width: number },
  pageCount: number,
  direction: ReadingDirection,
): number {
  return pageFromScrubRatio(scrubRatioFromPointer(clientX, rect, direction), pageCount);
}

/**
 * Parse the jump-to-page field. Returns null for anything that is not a whole
 * page number so a half-typed value never yanks the reader somewhere.
 */
export function parsePageInput(raw: string, pageCount: number): number | null {
  if (!Number.isFinite(pageCount) || pageCount <= 0) return null;
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return null;
  return Math.min(Math.floor(pageCount), Math.max(1, value));
}
