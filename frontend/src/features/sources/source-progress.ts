import { useCallback, useMemo, useRef, useSyncExternalStore } from "react";
import {
  activeStorageKey,
  claimLegacyValue,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";

/**
 * Client-side reading progress for online-source chapters. The backend has no
 * per-chapter read model for remote sources, so we persist a lightweight record
 * in localStorage under a single object, keyed by
 * `sourceId:seriesId:chapterId`. Mirrors the SSR-safe style of scroll-storage.
 *
 * The object itself is per (user, profile) — reading position is exactly the
 * kind of data profiles isolate server-side, and the source migration replays
 * remote reading positions into it, so a device-global object showed one
 * profile where another had got to.
 */

const STORAGE_BASE = "mm.source-progress";

/**
 * The key this store used before it was scoped. Scoped keys carry a
 * `::u<user>:p<profile>` suffix, so the bare base can only ever be the
 * pre-scoping blob. See {@link adoptLegacySourceProgress}.
 */
const LEGACY_STORAGE_KEY = STORAGE_BASE;

export interface SourceChapterProgress {
  page: number;
  pageCount: number;
  completed: boolean;
  updatedAt: string;
}

export type SourceSeriesProgressMap = Record<string, SourceChapterProgress>;

/** The whole localStorage object, keyed by `sourceId:seriesId:chapterId`. */
export type SourceProgressStore = Record<string, SourceChapterProgress>;

type ProgressStore = SourceProgressStore;

function recordKey(sourceId: string, seriesId: string, chapterId: string): string {
  return `${sourceId}:${seriesId}:${chapterId}`;
}

function seriesPrefix(sourceId: string, seriesId: string): string {
  return `${sourceId}:${seriesId}:`;
}

function parseStore(raw: string | null): ProgressStore {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed && typeof parsed === "object") {
      return parsed as ProgressStore;
    }
    return {};
  } catch {
    return {};
  }
}

/** Empty with no active profile: there is no unscoped store to fall back to. */
function readStore(): ProgressStore {
  return parseStore(readScopedString(STORAGE_BASE));
}

function writeStore(store: ProgressStore): void {
  // Dropped with no active profile rather than parked under a shared key.
  writeScopedString(STORAGE_BASE, JSON.stringify(store));
}

/**
 * Fold a pre-scoping store into a scoped one, newer-wins.
 *
 * Same rule as {@link applyProgressRemap}: a record already in the scope was
 * written after the upgrade, so it reflects where the profile actually is and
 * an older legacy record must not walk it back.
 */
export function mergeLegacyProgress(
  scoped: SourceProgressStore,
  legacy: SourceProgressStore,
): { store: SourceProgressStore; adopted: number } {
  const next: SourceProgressStore = { ...scoped };
  let adopted = 0;

  for (const [key, record] of Object.entries(legacy)) {
    const existing = next[key];
    if (existing && existing.updatedAt >= record.updatedAt) {
      continue;
    }
    next[key] = record;
    adopted += 1;
  }

  return { store: next, adopted };
}

/**
 * Hand the pre-scoping `mm.source-progress` blob to the active profile, once.
 * Returns how many chapter records it took over.
 *
 * Adopted rather than discarded, unlike recent searches: these records are the
 * ONLY copy of where the user is in a remote series — the backend has no
 * per-chapter read model for online sources, so dropping them silently resets
 * every followed remote series to page one with nothing to restore from.
 *
 * The first profile active after the upgrade claims it and the unscoped key is
 * removed in the same step, so a second profile inherits nothing. That is the
 * furthest the data can honestly be attributed: it was written while the device
 * had a single identity, and the person resuming on it is the one who left it.
 */
export function adoptLegacySourceProgress(): number {
  const raw = claimLegacyValue(LEGACY_STORAGE_KEY);
  if (raw === null) {
    return 0;
  }
  const { store, adopted } = mergeLegacyProgress(readStore(), parseStore(raw));
  if (adopted > 0) {
    writeStore(store);
  }
  return adopted;
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

/** A `(source, series)` pair, as a source migration names them. */
export interface SourceSeriesRef {
  source: string;
  seriesId: string;
}

/**
 * Replay a migration's chapter map over a progress store.
 *
 * Online reading progress for a non-downloaded remote series exists ONLY here —
 * the backend has no per-chapter read model for remote sources — so repointing
 * a follow at another source leaves the user's place behind unless the client
 * moves it. The server hands back the number-matched remap for exactly this.
 *
 * Copies rather than moves: the records under the old `(source, series)` are
 * left in place, so migrating back (or reading the old source directly, which
 * still routes) does not lose anything, and re-running the same remap is a
 * no-op. A target that already has *newer* progress is never overwritten —
 * nearest-match can collapse two old chapters onto one target, and the most
 * recently read of them is the one that reflects where the user actually is.
 */
export function applyProgressRemap(
  store: SourceProgressStore,
  from: SourceSeriesRef,
  to: SourceSeriesRef,
  chapterMap: ReadonlyArray<{ from_chapter_id: string; to_chapter_id: string | null }>,
): { store: SourceProgressStore; moved: number } {
  const next: SourceProgressStore = { ...store };
  let moved = 0;

  for (const entry of chapterMap) {
    if (!entry.to_chapter_id) {
      continue;
    }
    const record = store[recordKey(from.source, from.seriesId, entry.from_chapter_id)];
    if (!record) {
      continue;
    }
    const targetKey = recordKey(to.source, to.seriesId, entry.to_chapter_id);
    const existing = next[targetKey];
    if (existing && existing.updatedAt >= record.updatedAt) {
      continue;
    }
    next[targetKey] = record;
    moved += 1;
  }

  return { store: next, moved };
}

/**
 * Persist {@link applyProgressRemap} against the active profile's store — the
 * migration was performed by that profile, and only its positions move.
 * Returns how many chapters carried their progress across.
 */
export function remapSourceSeriesProgress(
  from: SourceSeriesRef,
  to: SourceSeriesRef,
  chapterMap: ReadonlyArray<{ from_chapter_id: string; to_chapter_id: string | null }>,
): number {
  if (typeof window === "undefined") {
    return 0;
  }
  const { store, moved } = applyProgressRemap(readStore(), from, to, chapterMap);
  if (moved > 0) {
    writeStore(store);
  }
  return moved;
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
      if (
        event instanceof StorageEvent &&
        event.key !== null &&
        event.key !== activeStorageKey(STORAGE_BASE)
      ) {
        return;
      }
      onChange();
    };
    window.addEventListener("storage", handler);
    window.addEventListener("focus", handler);
    // A profile switch changes which key this reads without touching storage,
    // so no DOM event announces it.
    const unsubscribeScope = subscribeStorageScope(onChange);
    return () => {
      window.removeEventListener("storage", handler);
      window.removeEventListener("focus", handler);
      unsubscribeScope();
    };
  }, []);

  // getSnapshot must return a stable reference until the underlying data
  // actually changes, so cache by raw storage string + scoped key + series key.
  const cacheRef = useRef<{
    raw: string | null;
    key: string;
    map: SourceSeriesProgressMap;
  } | null>(null);

  const getSnapshot = useCallback(() => {
    const raw = readScopedString(STORAGE_BASE);
    const key = `${activeStorageKey(STORAGE_BASE) ?? ""}|${sourceId}:${seriesId}`;
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
