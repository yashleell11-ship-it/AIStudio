"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import { useBootstrapStatus } from "@/features/auth/hooks";
import { isNovelsEnabled, resolveNovelsEnabled, sourceKindsKnown } from "@/features/novels/gate";
import { useSources } from "@/features/sources/hooks";
import {
  buildSourceModeIndex,
  filterByContentMode,
  filterSourcesByContentMode,
  matchesContentMode,
  resolveContentMode,
  type ContentMode,
} from "./mode";
import {
  getContentModeServerSnapshot,
  getContentModeSnapshot,
  subscribeContentMode,
  writeContentMode,
} from "./store";
import type { SourceSummary } from "@/features/sources/types";

export interface ContentModeState {
  /** The mode in force — always `"manga"` while novels are disabled. */
  mode: ContentMode;
  setMode: (mode: ContentMode) => void;
  /**
   * Whether the server has novels turned on. False hides the switch entirely
   * (not disables it): with the flag off there is no second mode to choose.
   */
  novelsEnabled: boolean;
}

/**
 * The app-wide Manga / Novels mode.
 *
 * `novels_enabled` rides on `GET /auth/bootstrap-status`, the public config
 * read the app already makes; the query is shared and cached, so reading it
 * from the sidebar and from a list screen costs one request.
 */
export function useContentMode(): ContentModeState {
  const { data: status } = useBootstrapStatus();
  const novelsEnabled = isNovelsEnabled(status);

  const stored = useSyncExternalStore(
    subscribeContentMode,
    getContentModeSnapshot,
    getContentModeServerSnapshot,
  );

  const mode = resolveContentMode(stored, novelsEnabled);
  const setMode = useCallback((next: ContentMode) => writeContentMode(next), []);

  return { mode, setMode, novelsEnabled };
}

export interface ContentModeFilter extends ContentModeState {
  /** Whether a row from this source belongs in the current mode. */
  keepSource: (sourceId: string | null | undefined) => boolean;
  /** Keep the rows of the current mode, reading each row's source id. */
  filterRows: <T>(
    rows: readonly T[] | undefined,
    getSourceId: (row: T) => string | null | undefined,
  ) => T[];
  /** Keep the sources of the current mode, straight off `content_kind`. */
  filterSources: (sources: readonly SourceSummary[] | undefined) => SourceSummary[];
  /**
   * False until `GET /sources` has answered, i.e. while row kinds are still
   * unknown. Screens that show an empty state use it to say "loading" rather
   * than "nothing here" for the frame before the index exists.
   */
  ready: boolean;
}

/**
 * Content-mode scoping for one list screen.
 *
 * Every filter here is a **no-op while novels are disabled** — not "filters to
 * manga", literally returns the input array. That is the production guarantee:
 * on a dark deployment these helpers cannot change what any screen renders,
 * however many of them are wired in.
 */
export function useContentModeFilter(): ContentModeFilter {
  const state = useContentMode();
  const { novelsEnabled, mode } = state;

  // Only pulled when novels are on. `useSources` is already fetched by half the
  // app and shared through the query cache, so this adds no request in
  // practice; `enabled` just keeps a dark deployment from making one at all.
  const sourcesQuery = useSources({ enabled: novelsEnabled });
  // `novelsEnabled` above is deliberately two-state: it decides whether novel
  // UI mounts at all, and "not yet" must mount nothing, same as "off". But
  // readiness is a different question, and answering it from the same two-state
  // read is what made this hook claim it was ready before the flag had arrived
  // — every consumer then scoped its lists against a mode resolved from a
  // default. `isPending` distinguishes an unanswered probe from a resolved off.
  const { data: bootstrapStatus, isPending: bootstrapPending } = useBootstrapStatus();
  const novelsResolved = resolveNovelsEnabled(bootstrapStatus, bootstrapPending);
  const index = useMemo(
    () => buildSourceModeIndex(novelsEnabled ? sourcesQuery.data : undefined),
    [novelsEnabled, sourcesQuery.data],
  );

  const keepSource = useCallback(
    (sourceId: string | null | undefined) =>
      !novelsEnabled || matchesContentMode(sourceId, index, mode),
    [index, mode, novelsEnabled],
  );

  const filterRows = useCallback(
    <T,>(
      rows: readonly T[] | undefined,
      getSourceId: (row: T) => string | null | undefined,
    ): T[] => {
      if (!rows) return [];
      if (!novelsEnabled) return rows as T[];
      return filterByContentMode(rows, index, mode, getSourceId);
    },
    [index, mode, novelsEnabled],
  );

  const filterSources = useCallback(
    (sources: readonly SourceSummary[] | undefined): SourceSummary[] => {
      if (!sources) return [];
      if (!novelsEnabled) return sources as SourceSummary[];
      return filterSourcesByContentMode(sources, mode);
    },
    [mode, novelsEnabled],
  );

  return {
    ...state,
    keepSource,
    filterRows,
    filterSources,
    ready: sourceKindsKnown(novelsResolved, sourcesQuery.data),
  };
}
