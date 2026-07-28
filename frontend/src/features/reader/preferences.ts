import {
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import { clampZoom } from "./fit";
import type { FitMode, ReadingDirection, ReadingMode } from "./types";

/**
 * Reading mode, fit and zoom are per-SERIES, not global: a webtoon wants the
 * continuous strip at fit-width, the manga next to it wants right-to-left
 * double-page spreads, and switching between them must not re-teach the reader
 * every time. The backend has no reader-preference model, so this lives in
 * localStorage under one namespaced object, keyed like source progress.
 *
 * Scoped per (user, profile) like every other client-side store: two personas
 * on one browser read different series, and inheriting a sibling's right-to-left
 * double-page setup is both wrong and a small disclosure that the sibling reads
 * that series at all. With no active profile there is no store rather than a
 * shared one.
 */

const STORAGE_KEY = "mm.reader-preferences";

export interface ReaderPreferences {
  readingMode: ReadingMode;
  fitMode: FitMode;
  direction: ReadingDirection;
  zoom: number;
}

export type ReaderPreferencesStore = Record<string, ReaderPreferences>;

export const DEFAULT_READER_PREFERENCES: ReaderPreferences = {
  readingMode: "continuous",
  fitMode: "width",
  direction: "ltr",
  zoom: 1,
};

const READING_MODES: ReadingMode[] = ["single", "double", "continuous"];
const FIT_MODES: FitMode[] = ["width", "height", "original"];
const DIRECTIONS: ReadingDirection[] = ["ltr", "rtl"];

/** Stable per-series key. Local library ids and source series ids never collide. */
export function readerSeriesKey(
  sourceId: string | null | undefined,
  seriesId: string | number,
): string {
  return `${sourceId ?? "local"}:${seriesId}`;
}

function pick<T extends string>(allowed: T[], value: unknown, fallback: T): T {
  return typeof value === "string" && (allowed as string[]).includes(value)
    ? (value as T)
    : fallback;
}

export function normalizeReaderPreferences(raw: unknown): ReaderPreferences {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_READER_PREFERENCES };
  const value = raw as Partial<Record<keyof ReaderPreferences, unknown>>;
  return {
    readingMode: pick(
      READING_MODES,
      value.readingMode,
      DEFAULT_READER_PREFERENCES.readingMode,
    ),
    fitMode: pick(FIT_MODES, value.fitMode, DEFAULT_READER_PREFERENCES.fitMode),
    direction: pick(DIRECTIONS, value.direction, DEFAULT_READER_PREFERENCES.direction),
    zoom: typeof value.zoom === "number" ? clampZoom(value.zoom) : DEFAULT_READER_PREFERENCES.zoom,
  };
}

/** Apply a patch to one series' entry, returning the whole next store. */
export function applyReaderPreferences(
  store: ReaderPreferencesStore,
  seriesKey: string,
  patch: Partial<ReaderPreferences>,
): ReaderPreferencesStore {
  const current = normalizeReaderPreferences(store[seriesKey]);
  return { ...store, [seriesKey]: normalizeReaderPreferences({ ...current, ...patch }) };
}

const listeners = new Set<() => void>();

/**
 * Subscription for `useSyncExternalStore`. localStorage is the store of record,
 * so a write in this tab notifies directly and a write in another tab arrives
 * through the `storage` event.
 */
export function subscribeReaderPreferences(listener: () => void): () => void {
  listeners.add(listener);
  // A profile switch changes which key this store reads from without touching
  // localStorage, so no `storage` event fires for it -- the scope subscription
  // is what makes the reader re-read rather than keep rendering the old
  // profile's mode.
  const unsubscribeScope = subscribeStorageScope(listener);
  if (typeof window !== "undefined") {
    window.addEventListener("storage", listener);
  }
  return () => {
    listeners.delete(listener);
    unsubscribeScope();
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", listener);
    }
  };
}

/** The raw serialized store, used as the cache key for a stable snapshot. */
export function readReaderPreferencesRaw(): string | null {
  return readScopedString(STORAGE_KEY);
}

function readStore(): ReaderPreferencesStore {
  const raw = readScopedString(STORAGE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as ReaderPreferencesStore) : {};
  } catch {
    return {};
  }
}

function writeStore(store: ReaderPreferencesStore): void {
  // writeScopedString drops the write when no profile is active, which is the
  // wanted behaviour: preferences are best-effort and must never be parked
  // under an unscoped key where another persona would inherit them.
  writeScopedString(STORAGE_KEY, JSON.stringify(store));
}

export function readReaderPreferences(seriesKey: string): ReaderPreferences {
  return normalizeReaderPreferences(readStore()[seriesKey]);
}

export function writeReaderPreferences(
  seriesKey: string,
  patch: Partial<ReaderPreferences>,
): ReaderPreferences {
  const next = applyReaderPreferences(readStore(), seriesKey, patch);
  writeStore(next);
  for (const listener of listeners) {
    listener();
  }
  return next[seriesKey];
}
