/**
 * The scroll offset applied before the strip mounts, for a chapter being
 * resumed.
 *
 * Only ever an ESTIMATE, and deliberately so: nothing is measured yet, so this
 * is the guess that stops the reader watching page one for a frame on the way
 * to page nine. The exact landing happens afterwards, through the strip's own
 * handle, which is the only thing that knows where a page really begins.
 *
 * It also keeps the shared app scroll container from reusing a stale position
 * from the route before (the library list, say).
 */
export interface ResumeEstimateInput {
  /** Where the reader left off: a page, and how far into it. */
  position: { page: number; offset: number } | null;
  pageCount: number;
  /** Estimated distance from the chapter's start to that page's top. */
  estimatedOffsetToPage: number;
}

export function estimateResumeOffset(input: ResumeEstimateInput): number {
  const { position, pageCount, estimatedOffsetToPage } = input;
  if (position == null || pageCount <= 0) {
    return 0;
  }
  const within = Math.max(0, position.offset);
  if (position.page <= 1) {
    return within;
  }
  return Math.max(0, estimatedOffsetToPage) + within;
}

const syncedScrollTargets = new Map<string, number>();

/**
 * Applies the target scroll offset when a chapter opens or reopens.
 * Re-syncs when the target offset changes (for example after leave and reopen)
 * but does not reset user scrolling on unrelated re-renders.
 */
export function syncChapterScroll(
  scrollKey: string,
  element: HTMLElement | null,
  scrollTop: number,
): void {
  if (!element) {
    return;
  }

  const previousTarget = syncedScrollTargets.get(scrollKey);
  if (previousTarget === scrollTop) {
    return;
  }

  if (element.scrollTop !== scrollTop) {
    element.scrollTop = scrollTop;
  }

  syncedScrollTargets.set(scrollKey, scrollTop);
}

/**
 * Re-applies a non-zero scroll offset after the virtualizer has measured content
 * height. Browsers can clamp scrollTop while content is still laying out.
 */
export function restoreChapterScroll(
  element: HTMLElement | null,
  scrollTop: number,
): boolean {
  if (!element || scrollTop <= 0 || element.scrollTop === scrollTop) {
    return false;
  }

  element.scrollTop = scrollTop;
  return true;
}

/**
 * Jump the reader container to an absolute offset. Unlike
 * {@link restoreChapterScroll} this also accepts 0, so a jump back to page one
 * is not silently dropped.
 */
export function setReaderScrollTop(
  element: HTMLElement | null,
  scrollTop: number,
): void {
  if (!element) return;
  const target = Math.max(0, Math.round(scrollTop));
  if (element.scrollTop === target) return;
  element.scrollTop = target;
}

/** Scroll the reader container by a delta, for the Space / Shift+Space keys. */
export function scrollReaderBy(element: HTMLElement | null, delta: number): void {
  if (!element || delta === 0) return;
  element.scrollBy({ top: delta, behavior: "smooth" });
}

/**
 * Advance the reader container by `distance` px in one animation-frame step —
 * auto-scroll's own driver (`use-auto-scroll.ts`). Unlike {@link scrollReaderBy}
 * this is an immediate, un-eased jump (each call is already one small step of
 * a continuous rAF loop, so easing it again would fight the loop's own
 * smoothing) and it hands back the resulting `scrollTop`, since the browser
 * may clamp it at the bottom of the content — the caller needs the real,
 * post-clamp value to tell its own pause-detection what to expect next.
 */
export function advanceReaderScroll(element: HTMLElement, distance: number): number {
  element.scrollTop = element.scrollTop + distance;
  return element.scrollTop;
}

export function clearChapterScrollPreparation(scrollKey: string): void {
  syncedScrollTargets.delete(scrollKey);
}

export function resetChapterScrollPreparationForTests(): void {
  syncedScrollTargets.clear();
}
