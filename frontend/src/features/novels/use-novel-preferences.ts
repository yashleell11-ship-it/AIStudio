"use client";

import { useCallback, useRef, useSyncExternalStore } from "react";
import {
  DEFAULT_NOVEL_PREFERENCES,
  readNovelPreferences,
  readNovelPreferencesRaw,
  subscribeNovelPreferences,
  writeNovelPreferences,
  type NovelPreferences,
} from "./preferences";

export interface NovelPreferencesController extends NovelPreferences {
  /**
   * False for the server render and the hydration pass, true once the stored
   * choice is readable. The reader holds the prose back until then, so a book
   * set to 24px never flashes a frame at the 19px default — a jump that is far
   * more disruptive in a wall of text than it is in a strip of images.
   */
  hydrated: boolean;
  update: (patch: Partial<NovelPreferences>) => void;
}

const onClient = () => true;
const onServer = () => false;

/**
 * This book's typography: size, leading, measure and face.
 *
 * Per series, and read through `useSyncExternalStore` over localStorage — the
 * same shape as the manga reader's `useReaderPreferences`, for the same reasons
 * (hydration-safe without mirroring into state; another tab's write lands here).
 */
export function useNovelPreferences(seriesKey: string): NovelPreferencesController {
  // getSnapshot must return a stable reference until the data really changes,
  // so the parsed value is cached against the raw string plus the series key.
  const cacheRef = useRef<{
    raw: string | null;
    seriesKey: string;
    value: NovelPreferences;
  } | null>(null);

  const getSnapshot = useCallback(() => {
    const raw = readNovelPreferencesRaw();
    let cache = cacheRef.current;
    if (!cache || cache.raw !== raw || cache.seriesKey !== seriesKey) {
      cache = { raw, seriesKey, value: readNovelPreferences(seriesKey) };
      cacheRef.current = cache;
    }
    return cache.value;
  }, [seriesKey]);

  const getServerSnapshot = useCallback(() => DEFAULT_NOVEL_PREFERENCES, []);

  const preferences = useSyncExternalStore(
    subscribeNovelPreferences,
    getSnapshot,
    getServerSnapshot,
  );
  const hydrated = useSyncExternalStore(subscribeNovelPreferences, onClient, onServer);

  const update = useCallback(
    (patch: Partial<NovelPreferences>) => {
      writeNovelPreferences(seriesKey, patch);
    },
    [seriesKey],
  );

  return { ...preferences, hydrated, update };
}
