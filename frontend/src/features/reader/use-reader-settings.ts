"use client";

import { useCallback, useSyncExternalStore } from "react";
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
}

/**
 * Per-profile reader chrome preferences (`pageGap`, `cinema`).
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

  return { ...settings, setPageGap, togglePageGap, setCinema, toggleCinema };
}
