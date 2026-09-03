import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";

/**
 * Per-profile reader chrome preferences that are the same wherever you read
 * (unlike reading mode / fit / zoom, which are per-series and owned by
 * `preferences.ts`).
 *
 * - `pageGap` — restore a thin separator between pages in the continuous strip.
 *   Default `false`: a webtoon must read as one seamless image.
 * - `cinema` — auto-hide ALL reader chrome after a few seconds of no activity,
 *   revealing it again on any tap / pointer-move / scroll-pause. Default `false`.
 *
 * Scoped per (user, profile) like every other client-side store here: two
 * personas on one browser should not inherit each other's reading furniture,
 * and a device-global key for per-profile data is the pattern that was
 * deliberately removed from the other reader stores.
 */

const STORAGE_BASE = "mm.reader-settings";

/** Same-tab notification; `storage` only fires in tabs that did not write. */
const SETTINGS_EVENT = "mm:reader-settings";

export interface ReaderSettings {
  pageGap: boolean;
  cinema: boolean;
}

export const DEFAULT_READER_SETTINGS: ReaderSettings = {
  pageGap: false,
  cinema: false,
};

export function parseReaderSettings(raw: string | null): ReaderSettings {
  if (!raw) return { ...DEFAULT_READER_SETTINGS };
  try {
    const parsed = JSON.parse(raw) as Partial<Record<keyof ReaderSettings, unknown>>;
    return {
      pageGap: parsed.pageGap === true,
      cinema: parsed.cinema === true,
    };
  } catch {
    return { ...DEFAULT_READER_SETTINGS };
  }
}

/** The stored settings for the active profile, or the defaults with no profile. */
export function readReaderSettings(): ReaderSettings {
  return parseReaderSettings(readScopedString(STORAGE_BASE));
}

export function writeReaderSettings(patch: Partial<ReaderSettings>): void {
  if (typeof window === "undefined") return;
  const next = { ...readReaderSettings(), ...patch };
  // writeScopedString drops the write when no profile is active, which is the
  // wanted behaviour: these are best-effort and must never be parked unscoped.
  writeScopedString(STORAGE_BASE, JSON.stringify(next));
  window.dispatchEvent(new Event(SETTINGS_EVENT));
}

// `useSyncExternalStore` compares snapshots by reference, so the parsed value is
// cached against the scoped key + raw string — a profile switch changes the key
// without touching localStorage and must still be noticed.
let snapshot: { key: string | null; raw: string | null; value: ReaderSettings } = {
  key: null,
  raw: null,
  value: DEFAULT_READER_SETTINGS,
};

export function getReaderSettingsSnapshot(): ReaderSettings {
  const key = activeStorageKey(STORAGE_BASE);
  const raw = readScopedString(STORAGE_BASE);
  if (snapshot.key !== key || snapshot.raw !== raw) {
    snapshot = { key, raw, value: parseReaderSettings(raw) };
  }
  return snapshot.value;
}

export function getReaderSettingsServerSnapshot(): ReaderSettings {
  return DEFAULT_READER_SETTINGS;
}

export function subscribeReaderSettings(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => onStoreChange();
  window.addEventListener(SETTINGS_EVENT, handler);
  window.addEventListener("storage", handler);
  const unsubscribeScope = subscribeStorageScope(handler);
  return () => {
    window.removeEventListener(SETTINGS_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
  };
}
