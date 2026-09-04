import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import { DESIGN_PRESET_META } from "@/features/preferences/presets";
import {
  activeDesignPreset,
  subscribeDesignPreset,
} from "@/features/preferences/preset-store";
import { type TapZone, type TapZoneConfig } from "./keymap";
import { clampDimmer, clampWarmth } from "./overlay";

/**
 * Per-profile reader chrome preferences that are the same wherever you read
 * (unlike reading mode / fit / zoom, which are per-series and owned by
 * `preferences.ts`).
 *
 * - `pageGap` — restore a thin separator between pages in the continuous strip.
 *   Default `false`: a webtoon must read as one seamless image.
 * - `cinema` — auto-hide ALL reader chrome after a few seconds of no activity,
 *   revealing it again on any tap / pointer-move / scroll-pause. Defaults to
 *   whatever the active DESIGN PRESET says: "how much furniture the reader
 *   shows" is one of the things a preset decides, and the Cinema preset exists
 *   to say "none of it". Only a default — the reader's own toggle wins for good
 *   the first time it is used.
 * - `dimmer` — night-reading darkening overlay, 0 (off) to `MAX_DIMMER`.
 * - `warmth` — night-reading amber tint overlay, 0 (off) to `MAX_WARMTH`.
 * - `pageTransition` — a subtle fade between paged-mode pages. Default
 *   `false`: a page turn is instant unless a reader opts into the polish, and
 *   `prefers-reduced-motion` collapses it to instant regardless (handled in
 *   CSS — see the `.reader-page-transition-enter` rule in `globals.css`).
 * - `tapZones` — customised left/centre/right tap behaviour, or `null` for
 *   "not customised yet", which the reader resolves to a mode-appropriate
 *   default itself (see `keymap.ts`) — this store only remembers an explicit
 *   choice, never a computed default, so it keeps following that default
 *   (including its own direction-flip for RTL) until the reader overrides it.
 *
 * These are ergonomic/physical preferences (how bright the screen looks, which
 * thumb taps where) rather than anything about a specific series, so — unlike
 * reading mode / fit / zoom — they belong here, not in `preferences.ts`.
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
  dimmer: number;
  warmth: number;
  pageTransition: boolean;
  tapZones: TapZoneConfig | null;
}

export const DEFAULT_READER_SETTINGS: ReaderSettings = {
  pageGap: false,
  cinema: false,
  dimmer: 0,
  warmth: 0,
  pageTransition: false,
  tapZones: null,
};

/** Whether the active design preset opens the reader with its chrome hidden. */
export function presetReaderCinema(): boolean {
  return DESIGN_PRESET_META[activeDesignPreset()].readerCinema;
}

/** The settings a profile that has never touched the reader starts from. */
export function presetReaderSettings(): ReaderSettings {
  return { ...DEFAULT_READER_SETTINGS, cinema: presetReaderCinema() };
}

const TAP_ZONE_ACTIONS: TapZone[] = ["advance", "retreat", "toggle"];

function isTapZone(value: unknown): value is TapZone {
  return typeof value === "string" && (TAP_ZONE_ACTIONS as string[]).includes(value);
}

function parseTapZones(value: unknown): TapZoneConfig | null {
  if (!value || typeof value !== "object") return null;
  const { left, center, right } = value as Partial<Record<keyof TapZoneConfig, unknown>>;
  if (!isTapZone(left) || !isTapZone(center) || !isTapZone(right)) return null;
  return { left, center, right };
}

export function parseReaderSettings(raw: string | null): ReaderSettings {
  const defaults = presetReaderSettings();
  if (!raw) return defaults;
  try {
    const parsed = JSON.parse(raw) as Partial<Record<keyof ReaderSettings, unknown>>;
    return {
      pageGap: parsed.pageGap === true,
      // Absent, not false: a stored blob always carries every key (see
      // `writeReaderSettings`), so `undefined` means this profile has never
      // expressed an opinion and the preset's default still applies.
      cinema: parsed.cinema === undefined ? defaults.cinema : parsed.cinema === true,
      dimmer: typeof parsed.dimmer === "number" ? clampDimmer(parsed.dimmer) : 0,
      warmth: typeof parsed.warmth === "number" ? clampWarmth(parsed.warmth) : 0,
      pageTransition: parsed.pageTransition === true,
      tapZones: parseTapZones(parsed.tapZones),
    };
  } catch {
    return defaults;
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
let snapshot: {
  key: string | null;
  raw: string | null;
  preset: string | null;
  value: ReaderSettings;
} = {
  key: null,
  raw: null,
  preset: null,
  value: DEFAULT_READER_SETTINGS,
};

export function getReaderSettingsSnapshot(): ReaderSettings {
  const key = activeStorageKey(STORAGE_BASE);
  const raw = readScopedString(STORAGE_BASE);
  // Part of the cache key: the preset supplies the cinema default, so a preset
  // change has to produce a new snapshot or the reader would keep its old
  // chrome until something else invalidated this.
  const preset = activeDesignPreset();
  if (snapshot.key !== key || snapshot.raw !== raw || snapshot.preset !== preset) {
    snapshot = { key, raw, preset, value: parseReaderSettings(raw) };
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
  const unsubscribePreset = subscribeDesignPreset(handler);
  return () => {
    window.removeEventListener(SETTINGS_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
    unsubscribePreset();
  };
}
