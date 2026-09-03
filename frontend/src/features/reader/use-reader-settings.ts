"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { TapZoneConfig } from "./keymap";
import { clampDimmer, clampWarmth } from "./overlay";
import {
  getReaderSettingsServerSnapshot,
  getReaderSettingsSnapshot,
  subscribeReaderSettings,
  writeReaderSettings,
  type ReaderSettings,
} from "./reader-settings";

export interface ReaderSettingsController extends ReaderSettings {
  setPageGap: (enabled: boolean) => void;
  togglePageGap: () => void;
  setCinema: (enabled: boolean) => void;
  toggleCinema: () => void;
  setPageTransition: (enabled: boolean) => void;
  togglePageTransition: () => void;
  /** Clamped to `[0, MAX_DIMMER]` — see `overlay.ts`. */
  setDimmer: (value: number) => void;
  /** Clamped to `[0, MAX_WARMTH]` — see `overlay.ts`. */
  setWarmth: (value: number) => void;
  setTapZones: (config: TapZoneConfig) => void;
}

/**
 * Per-profile reader chrome preferences (`pageGap`, `cinema`, `pageTransition`,
 * night-reading `dimmer`/`warmth`, and `tapZones` — see `reader-settings.ts`).
 *
 * Backed by `useSyncExternalStore` over scoped localStorage: hydration-safe
 * without mirroring into component state, and a profile switch or another tab's
 * write both land here.
 */
export function useReaderSettings(): ReaderSettingsController {
  const settings = useSyncExternalStore(
    subscribeReaderSettings,
    getReaderSettingsSnapshot,
    getReaderSettingsServerSnapshot,
  );

  const setPageGap = useCallback((enabled: boolean) => {
    writeReaderSettings({ pageGap: enabled });
  }, []);
  const togglePageGap = useCallback(() => {
    writeReaderSettings({ pageGap: !getReaderSettingsSnapshot().pageGap });
  }, []);
  const setCinema = useCallback((enabled: boolean) => {
    writeReaderSettings({ cinema: enabled });
  }, []);
  const toggleCinema = useCallback(() => {
    writeReaderSettings({ cinema: !getReaderSettingsSnapshot().cinema });
  }, []);
  const setPageTransition = useCallback((enabled: boolean) => {
    writeReaderSettings({ pageTransition: enabled });
  }, []);
  const togglePageTransition = useCallback(() => {
    writeReaderSettings({ pageTransition: !getReaderSettingsSnapshot().pageTransition });
  }, []);
  const setDimmer = useCallback((value: number) => {
    writeReaderSettings({ dimmer: clampDimmer(value) });
  }, []);
  const setWarmth = useCallback((value: number) => {
    writeReaderSettings({ warmth: clampWarmth(value) });
  }, []);
  const setTapZones = useCallback((config: TapZoneConfig) => {
    writeReaderSettings({ tapZones: config });
  }, []);

  return {
    ...settings,
    setPageGap,
    togglePageGap,
    setCinema,
    toggleCinema,
    setPageTransition,
    togglePageTransition,
    setDimmer,
    setWarmth,
    setTapZones,
  };
}
