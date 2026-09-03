"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { TriangleAlert, WifiOff } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { cn } from "@/lib/cn";
import { BulkActionBar } from "./BulkActionBar";
import { ContinueReading } from "./ContinueReading";
import { LibraryToolbar } from "./LibraryToolbar";
import { SeriesGrid } from "./SeriesGrid";
import {
  getLibraryDensityServerSnapshot,
  getLibraryDensitySnapshot,
  type LibraryDensity,
  subscribeLibraryDensity,
  writeLibraryDensity,
} from "../density";
import {
  type BulkAction,
  useBulkSeriesAction,
  useContinueReading,
  useSeriesList,
  useTags,
} from "../hooks";
import {
  EMPTY_SELECTION,
  extendSelection,
  orderedSelection,
  retainSelection,
  selectAll,
  type SelectionState,
  toggleSelection,
} from "../selection";
import {
  type LibraryQuery,
  hasActiveFilters,
  libraryQueryToListParams,
} from "../url-state";
import { useLibraryUrlState } from "../use-library-url-state";
import type { FollowedSeries } from "../types";

/** The server's ceiling (`GET /library/series` `per_page` le 200). */
const PAGE_SIZE = 200;
const SEARCH_DEBOUNCE_MS = 300;

/**
 * The full, filterable view of the profile's library (`/library/browse`).
 * Source-native: the library is the `followed_series` set, so this is the shelf
 * with search, sort, reading-status and favourite filters plus multi-select
 * bulk actions.
 */
export function LibraryView() {
  const { query, setQuery } = useLibraryUrlState();
  const [selectMode, setSelectMode] = useState(false);
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);

  const [searchInput, setSearchInput] = useState(query.search);
  const [committedSearch, setCommittedSearch] = useState(query.search);

  if (query.search !== committedSearch) {
    setCommittedSearch(query.search);
    setSearchInput(query.search);
  }

  useEffect(() => {
    const trimmed = searchInput.trim();
    if (trimmed === query.search) return;
    const timer = setTimeout(() => {
      setCommittedSearch(trimmed);
      setQuery({ ...query, search: trimmed }, { replace: true });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [searchInput, query, setQuery]);

  const density = useSyncExternalStore(
    subscribeLibraryDensity,
    getLibraryDensitySnapshot,
    getLibraryDensityServerSnapshot,
  );

  const listParams = useMemo(
    () => libraryQueryToListParams(query, { page: 1, per_page: PAGE_SIZE }),
    [query],
  );
  const seriesQuery = useSeriesList(listParams);
  const continueQuery = useContinueReading(12);
  const tagsQuery = useTags();
  const bulk = useBulkSeriesAction();

  const items = useMemo<FollowedSeries[]>(
    () => seriesQuery.data?.items ?? [],
    [seriesQuery.data],
  );
  const byId = useMemo(() => {
    const map = new Map<number, FollowedSeries>();
    for (const series of items) map.set(series.id, series);
    return map;
  }, [items]);
  const orderedIds = useMemo(() => items.map((series) => series.id), [items]);
  const seriesCount = seriesQuery.data?.total ?? items.length;

  const [renderedIds, setRenderedIds] = useState(orderedIds);
  if (renderedIds !== orderedIds) {
    setRenderedIds(orderedIds);
    setSelection((current) => retainSelection(current, orderedIds));
  }

  const handleSelect = useCallback(
    (seriesId: number, shiftKey: boolean) => {
      setSelection((current) =>
        shiftKey
          ? extendSelection(current, seriesId, orderedIds)
          : toggleSelection(current, seriesId),
      );
    },
    [orderedIds],
  );

  const selectedCount = selection.ids.size;
  const selecting = selectMode || selectedCount > 0;

  const clearSelection = useCallback(() => {
    setSelection(EMPTY_SELECTION);
    setSelectMode(false);
  }, []);

  const runBulkAction = useCallback(
    async (action: BulkAction) => {
      const ids = orderedSelection(selection, orderedIds);
      const rows = ids
        .map((id) => byId.get(id))
        .filter((row): row is FollowedSeries => row !== undefined);
      if (rows.length === 0) return;
      await bulk.run(action, rows);
      clearSelection();
    },
    [bulk, byId, clearSelection, orderedIds, selection],
  );

  const setDensity = useCallback((next: LibraryDensity) => {
    writeLibraryDensity(next);
  }, []);

  const applyQuery = useCallback(
    (next: LibraryQuery) => {
      clearSelection();
      setQuery(next);
    },
    [clearSelection, setQuery],
  );

  const isSearching = query.search.length > 0;
  const filtersActive = hasActiveFilters(query);
  const isLanding = !isSearching && !filtersActive;

  const viewState = resolveViewState({
    isLoading: seriesQuery.isLoading,
    error: seriesQuery.error,
    isEmpty: items.length === 0,
  });

  const emptyState = isSearching ? "search" : filtersActive ? "filter" : "library";

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div
        className={cn(
          "mx-auto max-w-[110rem]",
          (selectedCount > 0 || bulk.message !== null) && "pb-24",
        )}
      >
        <LibraryToolbar
          query={query}
          onQueryChange={applyQuery}
          searchInput={searchInput}
          onSearchInputChange={setSearchInput}
          density={density}
          onDensityChange={setDensity}
          selecting={selecting}
          onSelectingChange={(next) => {
            if (next) setSelectMode(true);
            else clearSelection();
          }}
          seriesCount={seriesCount}
          tags={tagsQuery.data ?? []}
        />

        {isLanding && viewState !== "offline" && viewState !== "error" ? (
          <ContinueReading
            items={continueQuery.data ?? []}
            isLoading={continueQuery.isLoading}
          />
        ) : null}

        {viewState === "offline" ? (
          <EmptyState
            tone="offline"
            icon={WifiOff}
            title="You're offline"
            description="Your library needs a connection to load. Chapters you've downloaded still open with no connection at all."
            action={{ label: "Go to Downloads", href: "/downloads" }}
          />
        ) : viewState === "error" ? (
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Couldn't load your library"
            description={apiErrorMessage(seriesQuery.error, "Something went wrong.")}
            action={{ label: "Try again", onClick: () => void seriesQuery.refetch() }}
          />
        ) : (
          <SeriesGrid
            items={items}
            isLoading={seriesQuery.isLoading}
            emptyState={emptyState}
            density={density}
            selection={{
              selecting,
              selectedIds: selection.ids,
              onSelect: handleSelect,
            }}
          />
        )}

        {!seriesQuery.isLoading && items.length < seriesCount ? (
          <p className="mt-6 text-center text-sm text-muted">
            Showing the first {items.length.toLocaleString()} of{" "}
            {seriesCount.toLocaleString()} series — narrow it with search or a
            filter.
          </p>
        ) : null}
      </div>

      <BulkActionBar
        count={selectedCount}
        visibleCount={items.length}
        allSelected={selectedCount === items.length && items.length > 0}
        running={bulk.isRunning}
        progress={bulk.progress}
        message={bulk.message}
        tags={tagsQuery.data ?? []}
        onRun={runBulkAction}
        onSelectAll={() => setSelection(selectAll(orderedIds))}
        onClear={clearSelection}
        onCancel={bulk.cancel}
        onDismissMessage={bulk.dismissMessage}
      />
    </div>
  );
}
