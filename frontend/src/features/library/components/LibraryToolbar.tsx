"use client";

import { useCallback, useRef, useState } from "react";
import {
  CheckSquare,
  Grid3X3,
  LayoutGrid,
  LayoutList,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import { DENSITY_LABELS, type LibraryDensity } from "@/features/library/density";
import {
  DEFAULT_LIBRARY_QUERY,
  type LibraryQuery,
  READING_STATUSES,
  type ReadingStatus,
  hasActiveFilters,
} from "@/features/library/url-state";
import type { SeriesFilter, SeriesSort, Tag } from "../types";

interface LibraryToolbarProps {
  query: LibraryQuery;
  onQueryChange: (next: LibraryQuery) => void;
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  density: LibraryDensity;
  onDensityChange: (density: LibraryDensity) => void;
  selecting: boolean;
  onSelectingChange: (selecting: boolean) => void;
  seriesCount: number;
  tags: Tag[];
}

const FILTER_CHIPS: { value: SeriesFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "reading", label: "Reading" },
  { value: "unread", label: "Not Started" },
  { value: "completed", label: "Completed" },
];

const SORT_OPTIONS: { value: SeriesSort; label: string }[] = [
  { value: "recently_updated", label: "Recently Updated" },
  { value: "recently_added", label: "Recently Added" },
  { value: "title", label: "Title" },
  { value: "sort_order", label: "Manual Order" },
];

const DENSITY_OPTIONS: {
  value: LibraryDensity;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { value: "comfortable", icon: LayoutGrid },
  { value: "compact", icon: Grid3X3 },
  { value: "list", icon: LayoutList },
];

const READING_STATUS_LABELS: Record<ReadingStatus, string> = {
  unread: "Unread",
  reading: "Reading",
  completed: "Completed",
  on_hold: "On hold",
  plan_to_read: "Plan to read",
  dropped: "Dropped",
};

export function LibraryToolbar({
  query,
  onQueryChange,
  searchInput,
  onSearchInputChange,
  density,
  onDensityChange,
  selecting,
  onSelectingChange,
  seriesCount,
}: LibraryToolbarProps) {
  const searchRef = useRef<HTMLInputElement>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);

  useShortcut({
    id: "library.focus-search",
    keys: "/",
    description: "Focus library search",
    group: "Library",
    handler: useCallback(() => {
      searchRef.current?.focus();
    }, []),
  });

  const patch = useCallback(
    (changes: Partial<LibraryQuery>) => onQueryChange({ ...query, ...changes }),
    [onQueryChange, query],
  );

  const filtersActive = hasActiveFilters(query);

  return (
    <div className="mb-6 space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <HeroHeading className="leading-none md:text-6xl">Library</HeroHeading>
          <p className="mt-2 text-sm text-muted">
            {seriesCount.toLocaleString()} series
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onSelectingChange(!selecting)}
            className={cn(
              "border border-border/50 bg-white/5 hover:bg-white/10",
              selecting && "border-primary/40 bg-primary/10 text-primary",
            )}
            aria-pressed={selecting}
          >
            <CheckSquare className="size-4" />
            {selecting ? "Done" : "Select"}
          </Button>

          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setFiltersOpen((open) => !open)}
            className={cn(
              "border border-border/50 bg-white/5 hover:bg-white/10",
              (filtersOpen || filtersActive) &&
                "border-primary/40 bg-primary/10 text-primary",
            )}
            aria-expanded={filtersOpen}
          >
            <SlidersHorizontal className="size-4" />
            Filters
          </Button>

          <select
            value={query.sort}
            onChange={(event) => patch({ sort: event.target.value as SeriesSort })}
            className="h-9 rounded-lg border border-border/50 bg-white/5 px-3 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            aria-label="Sort library"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <div
            className="flex rounded-lg border border-border/50 bg-white/5 p-0.5"
            role="group"
            aria-label="Grid density"
          >
            {DENSITY_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onDensityChange(option.value)}
                className={cn(
                  "flex size-8 items-center justify-center rounded-md transition-colors",
                  density === option.value
                    ? "bg-primary text-primary-fg"
                    : "text-muted hover:text-fg",
                )}
                aria-label={`${DENSITY_LABELS[option.value]} density`}
                title={DENSITY_LABELS[option.value]}
                aria-pressed={density === option.value}
              >
                <option.icon className="size-4" />
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <Input
          ref={searchRef}
          value={searchInput}
          onChange={(event) => onSearchInputChange(event.target.value)}
          placeholder="Search by title..."
          className="h-11 border-border/50 bg-white/[0.03] pl-11 focus-visible:ring-primary/40"
          aria-label="Search library"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTER_CHIPS.map((chip) => {
          const active = query.status === chip.value;
          return (
            <button
              key={chip.value}
              type="button"
              onClick={() => patch({ status: chip.value })}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-fg shadow-glow"
                  : "bg-white/5 text-muted hover:bg-white/10 hover:text-fg",
              )}
              aria-pressed={active}
            >
              {chip.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => patch({ is_favorite: query.is_favorite === true ? null : true })}
          className={cn(
            "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
            query.is_favorite === true
              ? "bg-primary/20 text-primary"
              : "bg-white/5 text-muted hover:bg-white/10 hover:text-fg",
          )}
          aria-pressed={query.is_favorite === true}
        >
          ★ Favorites
        </button>
      </div>

      {filtersOpen ? (
        <div className="glass-panel flex flex-wrap items-end gap-4 rounded-xl p-4">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Shelf status
            <select
              value={query.reading_status ?? ""}
              onChange={(event) =>
                patch({
                  reading_status: event.target.value
                    ? (event.target.value as ReadingStatus)
                    : null,
                })
              }
              className="h-9 rounded-lg border border-border/50 bg-white/5 px-3 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <option value="">Any</option>
              {READING_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {READING_STATUS_LABELS[status]}
                </option>
              ))}
            </select>
          </label>

          {filtersActive ? (
            <Button
              type="button"
              variant="ghost"
              onClick={() =>
                onQueryChange({
                  ...DEFAULT_LIBRARY_QUERY,
                  search: query.search,
                  sort: query.sort,
                })
              }
            >
              Clear filters
            </Button>
          ) : null}

          <p className="w-full text-xs text-muted">
            Press <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono">/</kbd> to
            focus search · shift-click a cover to select a range
          </p>
        </div>
      ) : null}
    </div>
  );
}
