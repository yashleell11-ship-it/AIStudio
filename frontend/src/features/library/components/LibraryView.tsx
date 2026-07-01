"use client";

import { useMemo, useState } from "react";
import { ApiError } from "@/types/api";
import { ImportDialog } from "./ImportDialog";
import { LibraryToolbar, type LibraryViewMode } from "./LibraryToolbar";
import { SeriesGrid } from "./SeriesGrid";
import { useSearch, useSeriesList } from "../hooks";
import type { SeriesFilter, SeriesSort } from "../types";

export function LibraryView() {
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SeriesSort>("updated");
  const [filter, setFilter] = useState<SeriesFilter>("all");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [viewMode, setViewMode] = useState<LibraryViewMode>("grid");

  const isSearching = search.trim().length > 0;

  const seriesQuery = useSeriesList({
    page: 1,
    per_page: 200,
    sort,
    search: isSearching ? undefined : search.trim() || undefined,
    status: filter,
    is_favorite: favoritesOnly || undefined,
  });

  const searchQuery = useSearch({
    q: search.trim(),
    page: 1,
    per_page: 40,
  });

  const items = useMemo(() => {
    if (isSearching && searchQuery.data) {
      return searchQuery.data.items;
    }
    return seriesQuery.data?.items ?? [];
  }, [isSearching, searchQuery.data, seriesQuery.data]);

  const seriesCount = useMemo(() => {
    if (isSearching && searchQuery.data) {
      return searchQuery.data.total;
    }
    return seriesQuery.data?.total ?? items.length;
  }, [isSearching, searchQuery.data, seriesQuery.data, items.length]);

  const isLoading = isSearching ? searchQuery.isLoading : seriesQuery.isLoading;
  const error = isSearching ? searchQuery.error : seriesQuery.error;

  const emptyState = isSearching
    ? "search"
    : favoritesOnly || filter !== "all"
      ? "filter"
      : "library";

  const errorMessage =
    error instanceof ApiError
      ? error.message
      : error
        ? "Failed to load library."
        : null;

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div className="mx-auto max-w-7xl">
        <LibraryToolbar
          search={search}
          onSearchChange={setSearch}
          sort={sort}
          onSortChange={setSort}
          filter={filter}
          onFilterChange={setFilter}
          favoritesOnly={favoritesOnly}
          onFavoritesChange={setFavoritesOnly}
          onImportClick={() => setImportOpen(true)}
          seriesCount={seriesCount}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />

        {errorMessage ? (
          <div className="mb-6 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        ) : null}

        <SeriesGrid
          items={items}
          isLoading={isLoading}
          emptyState={emptyState}
          viewMode={viewMode}
        />

        <ImportDialog open={importOpen} onClose={() => setImportOpen(false)} />
      </div>
    </div>
  );
}
