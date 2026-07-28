"use client";

import { useCallback, useRef, useSyncExternalStore } from "react";
import {
  DEFAULT_READER_PREFERENCES,
  readReaderPreferences,
  readReaderPreferencesRaw,
  subscribeReaderPreferences,
  writeReaderPreferences,
  type ReaderPreferences,
} from "./preferences";

export interface ReaderPreferencesController extends ReaderPreferences {
  /**
   * False for the server render and the hydration pass, true once the stored
   * choice is readable. Callers hold the reader back until then so a series set
   * to spreads never flashes a frame of the default strip.
   */
  hydrated: boolean;
  update: (patch: Partial<ReaderPreferences>) => void;
}

const onClient = () => true;
const onServer = () => false;

/**
 * The active series' reading mode, fit, direction and zoom.
 *
 * Backed by `useSyncExternalStore` over localStorage: it is hydration-safe
 * without mirroring the stored value into component state, and a change made in
 * another tab lands here too.
 */
export function useReaderPreferences(seriesKey: string): ReaderPreferencesController {
  // getSnapshot must return a stable reference until the data really changes,
  // so the parsed value is cached against the raw string plus the series key.
  const cacheRef = useRef<{
    raw: string | null;
    seriesKey: string;
    value: ReaderPreferences;
  } | null>(null);

  const getSnapshot = useCallback(() => {
    const raw = readReaderPreferencesRaw();
    let cache = cacheRef.current;
    if (!cache || cache.raw !== raw || cache.seriesKey !== seriesKey) {
      cache = { raw, seriesKey, value: readReaderPreferences(seriesKey) };
      cacheRef.current = cache;
    }
    return cache.value;
  }, [seriesKey]);

  const getServerSnapshot = useCallback(() => DEFAULT_READER_PREFERENCES, []);

  const preferences = useSyncExternalStore(
    subscribeReaderPreferences,
    getSnapshot,
    getServerSnapshot,
  );
  const hydrated = useSyncExternalStore(subscribeReaderPreferences, onClient, onServer);

  const update = useCallback(
    (patch: Partial<ReaderPreferences>) => {
      writeReaderPreferences(seriesKey, patch);
    },
    [seriesKey],
  );

  return { ...preferences, hydrated, update };
}
