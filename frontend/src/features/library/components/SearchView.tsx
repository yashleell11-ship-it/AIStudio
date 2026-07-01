"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError } from "@/types/api";
import { Input } from "@/components/ui/input";
import { useShortcut } from "@/lib/keyboard";
import { useSearch } from "@/features/library/hooks";
import { SeriesGrid } from "./SeriesGrid";

export function SearchView() {
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const searchQuery = useSearch({ q: query.trim(), page: 1, per_page: 40 });

  useShortcut({
    id: "search.focus-input",
    keys: "/",
    description: "Focus search",
    group: "Search",
    handler: useCallback(() => {
      searchRef.current?.focus();
    }, []),
  });

  const errorMessage =
    searchQuery.error instanceof ApiError
      ? searchQuery.error.message
      : searchQuery.error
        ? "Search failed. Please try again."
        : null;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-fg">Search</h1>
        <p className="mt-1 text-sm text-muted">
          Search across titles, authors, and descriptions. Press <kbd className="rounded bg-surface-2 px-1.5 py-0.5 text-xs">/</kbd> to focus.
        </p>
      </div>

      <div className="mb-6">
        <Input
          ref={searchRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search your library…"
          className="w-full sm:w-96"
          aria-label="Search library"
        />
      </div>

      {errorMessage && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {errorMessage}
        </div>
      )}

      {query.trim().length > 0 && (
        <>
          {searchQuery.isLoading ? (
            <SeriesGrid items={[]} isLoading emptyState="search" />
          ) : searchQuery.data && searchQuery.data.items.length === 0 ? (
            <SeriesGrid items={[]} emptyState="search" />
          ) : (
            <>
              <p className="mb-4 text-sm text-muted">
                {searchQuery.data?.total ?? 0} results found
              </p>
              <SeriesGrid items={searchQuery.data?.items ?? []} isLoading={false} />
            </>
          )}
        </>
      )}

      {query.trim().length === 0 && (
        <div className="rounded-xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-lg font-medium text-fg">Start typing to search</p>
          <p className="mt-2 text-sm text-muted">
            Search across titles, authors, and descriptions in your library.
          </p>
        </div>
      )}
    </div>
  );
}
