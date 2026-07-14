import { useCallback, useMemo, useRef, useSyncExternalStore } from "react";

/**
 * Client-side reading progress for online-source chapters. The backend has no
 * per-chapter read model for remote sources, so we persist a lightweight record
 * in localStorage under a single namespaced object, keyed by
 * `sourceId:seriesId:chapterId`. Mirrors the SSR-safe style of scroll-storage.
 */

const STORAGE_KEY = "mm.source-progress";

export interface SourceChapterProgress {
  page: number;
  pageCount: number;
  completed: boolean;
  updatedAt: string;
}

export type SourceSeriesProgressMap = Record<string, SourceChapterProgress>;

type ProgressStore = Record<string, SourceChapterProgress>;

function recordKey(sourceId: string, seriesId: string, chapterId: string): string {
  return `${sourceId}:${seriesId}:${chapterId}`;
}

function seriesPrefix(sourceId: string, seriesId: string): string {
  return `${sourceId}:${seriesId}:`;
}

function readStore(): ProgressStore {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") {
      return parsed as ProgressStore;
    }
    return {};
  } catch {
    return {};
  }
}

function writeStore(store: ProgressStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Ignore quota / serialization failures — progress is best-effort.
  }
}

export function getSourceChapterProgress(
  sourceId: string,
  seriesId: string,
  chapterId: string,
): SourceChapterProgress | null {
  return readStore()[recordKey(sourceId, seriesId, chapterId)] ?? null;
}

export function setSourceChapterProgress(
  sourceId: string,
  seriesId: string,
  chapterId: string,
  { page, pageCount }: { page: number; pageCount: number },
): void {
  if (typeof window === "undefined") return;
  const safePage = Math.max(1, Math.round(page));
  const safeCount = Math.max(0, Math.round(pageCount));
  const store = readStore();
  store[recordKey(sourceId, seriesId, chapterId)] = {
    page: safePage,
    pageCount: safeCount,
    completed: safeCount > 0 && safePage >= safeCount,
    updatedAt: new Date().toISOString(),
  };
  writeStore(store);
}

export function getSourceSeriesProgress(
  sourceId: string,
  seriesId: string,
): SourceSeriesProgressMap {
  const prefix = seriesPrefix(sourceId, seriesId);
  const result: SourceSeriesProgressMap = {};
  for (const [key, value] of Object.entries(readStore())) {
    if (key.startsWith(prefix)) {
      result[key.slice(prefix.length)] = value;
    }
  }
  return result;
}

export function getLatestReadChapter(
  sourceId: string,
  seriesId: string,
): { chapterId: string; progress: SourceChapterProgress } | null {
  return pickLatest(getSourceSeriesProgress(sourceId, seriesId));
}

function pickLatest(
  map: SourceSeriesProgressMap,
): { chapterId: string; progress: SourceChapterProgress } | null {
  let latest: { chapterId: string; progress: SourceChapterProgress } | null = null;
  for (const [chapterId, progress] of Object.entries(map)) {
    if (!latest || progress.updatedAt > latest.progress.updatedAt) {
      latest = { chapterId, progress };
    }
  }
  return latest;
}

const EMPTY_PROGRESS: SourceSeriesProgressMap = {};

/**
 * Reads the per-series progress map and keeps it fresh: re-reads on cross-tab
 * `storage` events and on window focus (so the series view reflects reading done
 * on a reader route once the user returns). Backed by useSyncExternalStore for
 * hydration-safe, tearing-free reads. Dependency-free.
 */
export function useSourceSeriesProgress(sourceId: string, seriesId: string) {
  const subscribe = useCallback((onChange: () => void) => {
    if (typeof window === "undefined") return () => {};
    const handler = (event: Event) => {
      if (event instanceof StorageEvent && event.key !== null && event.key !== STORAGE_KEY) {
        return;
      }
      onChange();
    };
    window.addEventListener("storage", handler);
    window.addEventListener("focus", handler);
    return () => {
      window.removeEventListener("storage", handler);
      window.removeEventListener("focus", handler);
    };
  }, []);

  // getSnapshot must return a stable reference until the underlying data
  // actually changes, so cache by raw storage string + series key.
  const cacheRef = useRef<{
    raw: string | null;
    key: string;
    map: SourceSeriesProgressMap;
  } | null>(null);

  const getSnapshot = useCallback(() => {
    const raw = typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY);
    const key = `${sourceId}:${seriesId}`;
    let cache = cacheRef.current;
    if (!cache || cache.raw !== raw || cache.key !== key) {
      cache = { raw, key, map: getSourceSeriesProgress(sourceId, seriesId) };
      cacheRef.current = cache;
    }
    return cache.map;
  }, [sourceId, seriesId]);

  const map = useSyncExternalStore(subscribe, getSnapshot, () => EMPTY_PROGRESS);
  const latest = useMemo(() => pickLatest(map), [map]);

  return { map, latest };
}
