import {
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import {
  clampFontSize,
  clampLineHeight,
  clampMeasure,
  DEFAULT_FONT_SIZE,
  DEFAULT_LINE_HEIGHT,
  DEFAULT_MEASURE,
  isNovelFontFamily,
  type NovelFontFamily,
} from "./typography";

/**
 * Typography, per SERIES — the same split the manga reader draws in
 * `features/reader/preferences.ts`.
 *
 * A dense translated web novel wants a bigger face and looser leading than a
 * crisply edited original; a reader who tuned one should not have to re-tune
 * it every time they move between the two. So size / leading / measure / face
 * are keyed by series, exactly like the manga reader's mode / fit / zoom.
 *
 * The reading PALETTE deliberately does not live here — it is a property of
 * the room and the hour, not of the book, so it is per-profile (`settings.ts`)
 * alongside the manga reader's dimmer and warmth.
 *
 * Scoped per (user, profile) like every other client-side store: two personas
 * on one browser read different things, and inheriting a sibling's setup is
 * both wrong and a small disclosure that the sibling reads that series at all.
 * With no active profile there is no store rather than a shared one.
 */

const STORAGE_KEY = "mm.novel-preferences";

export interface NovelPreferences {
  fontSize: number;
  lineHeight: number;
  /** Column width in `ch` — see `typography.ts`. */
  measure: number;
  fontFamily: NovelFontFamily;
}

export type NovelPreferencesStore = Record<string, NovelPreferences>;

export const DEFAULT_NOVEL_PREFERENCES: NovelPreferences = {
  fontSize: DEFAULT_FONT_SIZE,
  lineHeight: DEFAULT_LINE_HEIGHT,
  measure: DEFAULT_MEASURE,
  fontFamily: "serif",
};

/** Stable per-series key, matching the manga reader's `readerSeriesKey`. */
export function novelSeriesKey(sourceId: string, seriesKey: string): string {
  return `${sourceId}:${seriesKey}`;
}

export function normalizeNovelPreferences(raw: unknown): NovelPreferences {
  if (!raw || typeof raw !== "object") return { ...DEFAULT_NOVEL_PREFERENCES };
  const value = raw as Partial<Record<keyof NovelPreferences, unknown>>;
  return {
    fontSize:
      typeof value.fontSize === "number"
        ? clampFontSize(value.fontSize)
        : DEFAULT_NOVEL_PREFERENCES.fontSize,
    lineHeight:
      typeof value.lineHeight === "number"
        ? clampLineHeight(value.lineHeight)
        : DEFAULT_NOVEL_PREFERENCES.lineHeight,
    measure:
      typeof value.measure === "number"
        ? clampMeasure(value.measure)
        : DEFAULT_NOVEL_PREFERENCES.measure,
    fontFamily: isNovelFontFamily(value.fontFamily)
      ? value.fontFamily
      : DEFAULT_NOVEL_PREFERENCES.fontFamily,
  };
}

/** Apply a patch to one series' entry, returning the whole next store. */
export function applyNovelPreferences(
  store: NovelPreferencesStore,
  seriesKey: string,
  patch: Partial<NovelPreferences>,
): NovelPreferencesStore {
  const current = normalizeNovelPreferences(store[seriesKey]);
  return {
    ...store,
    [seriesKey]: normalizeNovelPreferences({ ...current, ...patch }),
  };
}

const listeners = new Set<() => void>();

/**
 * Subscription for `useSyncExternalStore`. localStorage is the store of record,
 * so a write in this tab notifies directly and a write in another tab arrives
 * through the `storage` event; a profile switch changes which key is read
 * without touching storage, so the scope subscription is needed too.
 */
export function subscribeNovelPreferences(listener: () => void): () => void {
  listeners.add(listener);
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
export function readNovelPreferencesRaw(): string | null {
  return readScopedString(STORAGE_KEY);
}

function readStore(): NovelPreferencesStore {
  const raw = readScopedString(STORAGE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object"
      ? (parsed as NovelPreferencesStore)
      : {};
  } catch {
    return {};
  }
}

function writeStore(store: NovelPreferencesStore): void {
  // writeScopedString drops the write when no profile is active, which is the
  // wanted behaviour: preferences are best-effort and must never be parked
  // under an unscoped key where another persona would inherit them.
  writeScopedString(STORAGE_KEY, JSON.stringify(store));
}

export function readNovelPreferences(seriesKey: string): NovelPreferences {
  return normalizeNovelPreferences(readStore()[seriesKey]);
}

export function writeNovelPreferences(
  seriesKey: string,
  patch: Partial<NovelPreferences>,
): NovelPreferences {
  const next = applyNovelPreferences(readStore(), seriesKey, patch);
  writeStore(next);
  for (const listener of listeners) {
    listener();
  }
  return next[seriesKey];
}
