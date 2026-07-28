/**
 * Resolves the scroll offset that must be applied before the virtual page list
 * mounts. Ensures the shared app scroll container does not reuse a stale position
 * from a previous route (for example the library list).
 */
export interface ScrollPreparationInput {
  savedScroll: number | null;
  initialPage: number;
  pageCount: number;
  estimatedOffsetToPage: number;
}

export function resolveInitialScrollTop(input: ScrollPreparationInput): number {
  const { savedScroll, initialPage, pageCount, estimatedOffsetToPage } = input;

  if (savedScroll != null) {
    return savedScroll;
  }

  if (initialPage > 1 && pageCount > 0) {
    return estimatedOffsetToPage;
  }

  return 0;
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

export function clearChapterScrollPreparation(scrollKey: string): void {
  syncedScrollTargets.delete(scrollKey);
}

export function resetChapterScrollPreparationForTests(): void {
  syncedScrollTargets.clear();
}
