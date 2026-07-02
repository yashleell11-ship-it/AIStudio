"use client";

import { useCallback, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useScrollContainer } from "@/lib/scroll-container";
import { useShortcut } from "@/lib/keyboard";
import { useSourceBrowseModes, useSourceSeries, useSources } from "../hooks";
import { SourceSeriesGrid } from "./SourceSeriesGrid";

interface SourceBrowserViewProps {
  sourceId: string;
}

function pageNumbers(current: number, total: number): number[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, index) => index + 1);
  }
  const pages = new Set<number>([1, total, current, current - 1, current + 1]);
  return [...pages].filter((page) => page >= 1 && page <= total).sort((a, b) => a - b);
}

export function SourceBrowserView({ sourceId }: SourceBrowserViewProps) {
  const sourcesQuery = useSources();
  const browseModesQuery = useSourceBrowseModes(sourceId);
  const sourceName =
    sourcesQuery.data?.find((source) => source.id === sourceId)?.name ?? sourceId;
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("default");
  const [page, setPage] = useState(1);
  const searchRef = useRef<HTMLInputElement>(null);
  const scrollContainer = useScrollContainer();

  const browseModes = browseModesQuery.data ?? [{ id: "default", label: "Browse" }];
  const activeSort = browseModes.some((mode) => mode.id === sort) ? sort : browseModes[0]?.id ?? "default";

  const seriesQuery = useSourceSeries(sourceId, {
    page,
    query: query || undefined,
    sort: activeSort !== "default" ? activeSort : undefined,
  });

  const data = seriesQuery.data;
  const items = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  const submitSearch = useCallback(() => {
    setQuery(search.trim());
    setPage(1);
  }, [search]);

  const goToPage = useCallback(
    (nextPage: number) => {
      if (nextPage < 1 || nextPage > totalPages) {
        return;
      }
      setPage(nextPage);
      if (scrollContainer) {
        scrollContainer.scrollTo({ top: 0, behavior: "smooth" });
      }
    },
    [scrollContainer, totalPages],
  );

  useShortcut({
    id: "sources.focus-search",
    keys: "/",
    description: "Focus source search",
    group: "Sources",
    handler: useCallback(() => {
      searchRef.current?.focus();
    }, []),
  });

  const visiblePages = pageNumbers(page, totalPages);

  return (
    <div className="p-6">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-fg">{sourceName}</h1>
          <p className="mt-1 text-sm text-muted">
            Browse and search this online source. Results come from the connector, not your
            local library.
          </p>
          {!seriesQuery.isLoading && items.length > 0 ? (
            <p className="mt-1 text-xs text-muted">
              Page {page} of {totalPages} · {total} series
              {query ? ` matching "${query}"` : ""}
            </p>
          ) : null}
        </div>
        <form
          className="flex w-full max-w-md gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            submitSearch();
          }}
        >
          <Input
            ref={searchRef}
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search this source…"
            aria-label="Search source"
          />
          <Button type="submit" className="shrink-0">
            Search
          </Button>
        </form>
      </div>

      {!query ? (
        <div className="mb-6 flex flex-wrap gap-2">
          {browseModes.map((mode) => (
            <Button
              key={mode.id}
              type="button"
              size="sm"
              variant={activeSort === mode.id ? "primary" : "secondary"}
              onClick={() => {
                setSort(mode.id);
                setPage(1);
              }}
            >
              {mode.label}
            </Button>
          ))}
        </div>
      ) : null}

      <SourceSeriesGrid
        sourceId={sourceId}
        items={items}
        isLoading={seriesQuery.isLoading}
        query={query}
        errorMessage={
          seriesQuery.error instanceof Error ? seriesQuery.error.message : undefined
        }
      />

      {totalPages > 1 && !seriesQuery.isLoading && !seriesQuery.isError ? (
        <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1 || seriesQuery.isFetching}
            onClick={() => goToPage(page - 1)}
          >
            Previous
          </Button>
          {visiblePages.map((pageNumber, index) => {
            const previous = visiblePages[index - 1];
            const showEllipsis = previous !== undefined && pageNumber - previous > 1;
            return (
              <span key={pageNumber} className="flex items-center gap-2">
                {showEllipsis ? <span className="px-1 text-muted">…</span> : null}
                <Button
                  variant={pageNumber === page ? "primary" : "secondary"}
                  size="sm"
                  disabled={seriesQuery.isFetching}
                  onClick={() => goToPage(pageNumber)}
                >
                  {pageNumber}
                </Button>
              </span>
            );
          })}
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= totalPages || seriesQuery.isFetching}
            onClick={() => goToPage(page + 1)}
          >
            Next
          </Button>
        </div>
      ) : null}
    </div>
  );
}
