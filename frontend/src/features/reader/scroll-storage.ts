const SCROLL_PREFIX = "manhwamaniacs-reader-scroll:";

function storageKey(chapterKey: string | number): string {
  return `${SCROLL_PREFIX}${chapterKey}`;
}

export function readScrollPosition(chapterKey: string | number): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(storageKey(chapterKey));
  if (raw == null) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

export function writeScrollPosition(chapterKey: string | number, scrollTop: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(storageKey(chapterKey), String(Math.round(scrollTop)));
}
