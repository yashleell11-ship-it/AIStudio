"use client";

import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import { BulkActionBar } from "./BulkActionBar";
import { ContinueReading } from "./ContinueReading";
import { DuplicateNotice } from "./DuplicateNotice";
import { ImportDialog } from "./ImportDialog";
import { LibraryToolbar } from "./LibraryToolbar";
import { SeriesGrid } from "./SeriesGrid";
import {
  getLibraryDensityServerSnapshot,
  getLibraryDensitySnapshot,
  type LibraryDensity,
  subscribeLibraryDensity,
  writeLibraryDensity,
} from "../density";
import { findDuplicateSeries } from "../duplicates";
import {
  type BulkAction,
  useBulkSeriesAction,
  useContinueReading,
  useSeriesList,
  useSetLibraryMembership,
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

/**
 * One large page rather than pagination: selection ranges, "select all" and
 * duplicate detection all mean "everything on screen", and a per_page the user
 * cannot see would quietly change what those mean. 200 is the server's ceiling
 * (backend/routes/library.py:148).
 */
const PAGE_SIZE = 200;

/** Long enough that a fast typist commits one URL, short enough to feel live. */
const SEARCH_DEBOUNCE_MS = 300;

export function LibraryView() {
  const { query, setQuery } = useLibraryUrlState();
  const [importOpen, setImportOpen] = useState(false);
  const [selectMode, setSelectMode] = useState(false);
  const [selection, setSelection] = useState<SelectionState>(EMPTY_SELECTION);
  const [undoIds, setUndoIds] = useState<number[] | null>(null);

  // The search box is the one control that changes on every keystroke, so it
  // keeps its own state and commits to the URL on a debounce (replacing, never
  // pushing). Everything else writes to the URL immediately.
  const [searchInput, setSearchInput] = useState(query.search);
  const [committedSearch, setCommittedSearch] = useState(query.search);

  // Back/forward (or a cleared filter set) changed the URL under us: adopt it.
  // Our own debounced commit records the value it wrote first, so this cannot
  // fire for it — otherwise every commit would snap the caret back and eat the
  // space the user just typed. Adjusting state during render is React's
  // recommended alternative to a setState-in-effect.
  if (query.search !== committedSearch) {
    setCommittedSearch(query.search);
    setSearchInput(query.search);
  }

  useEffect(() => {
    const trimmed = searchInput.trim();
    if (trimmed === query.search) {
      return;
    }
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

  // One request for every view, searching or not. The grid used to switch to
  // `GET /library/search` the moment the box had text, which silently dropped
  // every filter and the sort — fine when nothing else was in the URL, wrong now
  // that the URL is a promise about what is on screen. `list_series(search=…)`
  // matches title and author and composes with the rest.
  const listParams = useMemo(
    () => libraryQueryToListParams(query, { page: 1, per_page: PAGE_SIZE }),
    [query],
  );
  const seriesQuery = useSeriesList(listParams);
  const continueQuery = useContinueReading(12);
  const tagsQuery = useTags();
  const setMembership = useSetLibraryMembership();
  const bulk = useBulkSeriesAction();

  const items = useMemo(() => seriesQuery.data?.items ?? [], [seriesQuery.data]);
  const orderedIds = useMemo(() => items.map((series) => series.id), [items]);
  const seriesCount = seriesQuery.data?.total ?? items.length;

  // A filter, a search or a refetch after a bulk action can take cards off the
  // screen. Dropping their ids keeps the count in the bar equal to the number
  // of highlighted covers, and keeps the next bulk action honest.
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
  // Selecting anything turns the grid into a selection surface, so a second
  // click lands where the first one did instead of navigating away.
  const selecting = selectMode || selectedCount > 0;

  const clearSelection = useCallback(() => {
    setSelection(EMPTY_SELECTION);
    setSelectMode(false);
  }, []);

  const runBulkAction = useCallback(
    async (action: BulkAction) => {
      const ids = orderedSelection(selection, orderedIds);
      if (ids.length === 0) {
        return;
      }
      const outcome = await bulk.run(action, ids);
      // Only a removal is undoable, and only because the backend keeps
      // favourite, shelf status and progress when membership goes
      // (backend/routes/library.py:228-232) — re-adding restores the shelf
      // exactly as it was.
      const undoable =
        action.kind === "membership" &&
        !action.inLibrary &&
        outcome.succeeded.length > 0;
      setUndoIds(undoable ? outcome.succeeded : null);
      clearSelection();
    },
    [bulk, clearSelection, orderedIds, selection],
  );

  const undoRemoval = useCallback(async () => {
    if (undoIds === null) {
      return;
    }
    const ids = undoIds;
    setUndoIds(null);
    await bulk.run({ kind: "membership", inLibrary: true }, ids);
  }, [bulk, undoIds]);

  const setDensity = useCallback((next: LibraryDensity) => {
    writeLibraryDensity(next);
  }, []);

  const applyQuery = useCallback(
    (next: LibraryQuery) => {
      // A narrower view can only invalidate a selection built in the wider one.
      clearSelection();
      setQuery(next);
    },
    [clearSelection, setQuery],
  );

  const isSearching = query.search.length > 0;
  const filtersActive = hasActiveFilters(query);
  // The landing view: no search, no filters. Both the resume rail and the
  // duplicate notice belong to it — under a filtered grid they would describe a
  // library the user is not currently looking at.
  const isLanding = !isSearching && !filtersActive;

  const duplicateGroups = useMemo(
    () => (isLanding ? findDuplicateSeries(items) : []),
    [isLanding, items],
  );

  const errorMessage =
    seriesQuery.error instanceof ApiError
      ? seriesQuery.error.message
      : seriesQuery.error
        ? "Failed to load library."
        : null;

  const emptyState = isSearching ? "search" : filtersActive ? "filter" : "library";

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div
        className={cn(
          "mx-auto max-w-[110rem]",
          // Room for the floating action bar so it never sits on the last row.
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
            if (next) {
              setSelectMode(true);
            } else {
              clearSelection();
            }
          }}
          onImportClick={() => setImportOpen(true)}
          seriesCount={seriesCount}
          tags={tagsQuery.data ?? []}
        />

        {errorMessage ? (
          <div className="mb-6 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        ) : null}

        {isLanding ? (
          <ContinueReading
            items={continueQuery.data ?? []}
            isLoading={continueQuery.isLoading}
          />
        ) : null}

        {isLanding ? (
          <DuplicateNotice
            groups={duplicateGroups}
            scanned={items.length}
            total={seriesCount}
            pendingId={
              setMembership.isPending
                ? (setMembership.variables?.seriesId ?? null)
                : null
            }
            onUnfollow={(seriesId) =>
              setMembership.mutate({ seriesId, inLibrary: false })
            }
          />
        ) : null}

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

        {/* The grid has always loaded one page and no more. Saying so beats a
            count in the header that disagrees with the number of covers. */}
        {!seriesQuery.isLoading && items.length < seriesCount ? (
          <p className="mt-6 text-center text-sm text-muted">
            Showing the first {items.length.toLocaleString()} of{" "}
            {seriesCount.toLocaleString()} series — narrow it with search or a
            filter.
          </p>
        ) : null}

        <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />
      </div>

      <BulkActionBar
        count={selectedCount}
        visibleCount={items.length}
        allSelected={selectedCount === items.length && items.length > 0}
        running={bulk.isRunning}
        progress={bulk.progress}
        message={bulk.message}
        undoAvailable={undoIds !== null}
        tags={tagsQuery.data ?? []}
        onRun={runBulkAction}
        onSelectAll={() => setSelection(selectAll(orderedIds))}
        onClear={clearSelection}
        onCancel={bulk.cancel}
        onUndo={undoRemoval}
        onDismissMessage={() => {
          setUndoIds(null);
          bulk.dismissMessage();
        }}
      />
    </div>
  );
}
