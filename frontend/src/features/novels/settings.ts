import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import { isNovelPaletteChoice, type NovelPaletteChoice } from "./palettes";

/**
 * The reading palette, per PROFILE.
 *
 * Unlike typography (which is about the book, so it is per-series — see
 * `preferences.ts`), the surface a page is painted on is about the room, the
 * hour and the reader's eyes. It should follow someone from novel to novel,
 * exactly as the manga reader's dimmer and warmth do in
 * `features/reader/reader-settings.ts`, which is where that line was drawn.
 *
 * `null` — nothing stored — is a real state, not a missing value: it means
 * "never chose one", and only then does the site theme seed Paper or Dusk
 * (`resolvePaletteChoice`). An explicit choice is never overridden by a theme
 * change, because a palette that flips when the app's theme flips is not an
 * independent palette.
 *
 * Scoped per (user, profile) like every other client-side store here.
 */

const STORAGE_BASE = "mm.novel-settings";

/** Same-tab notification; `storage` only fires in tabs that did not write. */
const SETTINGS_EVENT = "mm:novel-settings";

export interface NovelSettings {
  /** `null` until the reader picks one — see the module note. */
  palette: NovelPaletteChoice | null;
}

export const DEFAULT_NOVEL_SETTINGS: NovelSettings = { palette: null };

export function parseNovelSettings(raw: string | null): NovelSettings {
  if (!raw) return { ...DEFAULT_NOVEL_SETTINGS };
  try {
    const parsed = JSON.parse(raw) as Partial<Record<keyof NovelSettings, unknown>>;
    return {
      palette: isNovelPaletteChoice(parsed.palette) ? parsed.palette : null,
    };
  } catch {
    return { ...DEFAULT_NOVEL_SETTINGS };
  }
}

/** The stored settings for the active profile, or the defaults with no profile. */
export function readNovelSettings(): NovelSettings {
  return parseNovelSettings(readScopedString(STORAGE_BASE));
}

export function writeNovelSettings(patch: Partial<NovelSettings>): void {
  if (typeof window === "undefined") return;
  const next = { ...readNovelSettings(), ...patch };
  writeScopedString(STORAGE_BASE, JSON.stringify(next));
  window.dispatchEvent(new Event(SETTINGS_EVENT));
}

// `useSyncExternalStore` compares snapshots by reference, so the parsed value is
// cached against the scoped key + raw string — a profile switch changes the key
// without touching localStorage and must still be noticed.
let snapshot: { key: string | null; raw: string | null; value: NovelSettings } = {
  key: null,
  raw: null,
  value: DEFAULT_NOVEL_SETTINGS,
};

export function getNovelSettingsSnapshot(): NovelSettings {
  const key = activeStorageKey(STORAGE_BASE);
  const raw = readScopedString(STORAGE_BASE);
  if (snapshot.key !== key || snapshot.raw !== raw) {
    snapshot = { key, raw, value: parseNovelSettings(raw) };
  }
  return snapshot.value;
}

export function getNovelSettingsServerSnapshot(): NovelSettings {
  return DEFAULT_NOVEL_SETTINGS;
}

export function subscribeNovelSettings(onStoreChange: () => void): () => void {
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
