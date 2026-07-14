"use client";

import { useCallback, useRef, useState } from "react";
import {
  Grid3X3,
  LayoutList,
  Search,
  SlidersHorizontal,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import type { SeriesFilter, SeriesSort } from "../types";

export type LibraryViewMode = "grid" | "list";

interface LibraryToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  sort: SeriesSort;
  onSortChange: (value: SeriesSort) => void;
  filter: SeriesFilter;
  onFilterChange: (value: SeriesFilter) => void;
  favoritesOnly: boolean;
  onFavoritesChange: (value: boolean) => void;
  onImportClick: () => void;
  seriesCount: number;
  viewMode: LibraryViewMode;
  onViewModeChange: (mode: LibraryViewMode) => void;
}

const FILTER_CHIPS: { value: SeriesFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "reading", label: "Reading" },
  { value: "unread", label: "Not Started" },
];

const SORT_OPTIONS: { value: SeriesSort; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "date_added", label: "Recently Added" },
  { value: "title", label: "Title" },
  { value: "recent", label: "Recently Read" },
  { value: "author", label: "Author" },
  { value: "year", label: "Year" },
  { value: "total_chapters", label: "Total Chapters" },
];

export function LibraryToolbar({
  search,
  onSearchChange,
  sort,
  onSortChange,
  filter,
  onFilterChange,
  favoritesOnly,
  onFavoritesChange,
  onImportClick,
  seriesCount,
  viewMode,
  onViewModeChange,
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

  useShortcut({
    id: "library.import",
    keys: "i",
    description: "Import library folder",
    group: "Library",
    handler: useCallback(() => {
      onImportClick();
    }, [onImportClick]),
  });

  return (
    <div className="mb-6 space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <HeroHeading className="text-[2.75rem] leading-none md:text-6xl">
            Library
          </HeroHeading>
          <p className="mt-2 text-sm text-muted">
            {seriesCount.toLocaleString()} series
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setFiltersOpen((open) => !open)}
            className={cn(
              "border border-border/50 bg-white/5 hover:bg-white/10",
              filtersOpen && "border-primary/40 bg-primary/10 text-primary",
            )}
            aria-expanded={filtersOpen}
          >
            <SlidersHorizontal className="size-4" />
            Filters
          </Button>

          <select
            value={sort}
            onChange={(event) => onSortChange(event.target.value as SeriesSort)}
            className="h-9 rounded-lg border border-border/50 bg-white/5 px-3 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            aria-label="Sort library"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>

          <div className="flex rounded-lg border border-border/50 bg-white/5 p-0.5">
            <button
              type="button"
              onClick={() => onViewModeChange("grid")}
              className={cn(
                "flex size-8 items-center justify-center rounded-md transition-colors",
                viewMode === "grid"
                  ? "bg-primary text-primary-fg"
                  : "text-muted hover:text-fg",
              )}
              aria-label="Grid view"
              aria-pressed={viewMode === "grid"}
            >
              <Grid3X3 className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => onViewModeChange("list")}
              className={cn(
                "flex size-8 items-center justify-center rounded-md transition-colors",
                viewMode === "list"
                  ? "bg-primary text-primary-fg"
                  : "text-muted hover:text-fg",
              )}
              aria-label="List view"
              aria-pressed={viewMode === "list"}
            >
              <LayoutList className="size-4" />
            </button>
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
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search by title, author, or tag..."
          className="h-11 border-border/50 bg-white/[0.03] pl-11 focus-visible:ring-primary/40"
          aria-label="Search library"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTER_CHIPS.map((chip) => {
          const active = filter === chip.value && !favoritesOnly;
          return (
            <button
              key={chip.value}
              type="button"
              onClick={() => {
                onFilterChange(chip.value);
                if (favoritesOnly) {
                  onFavoritesChange(false);
                }
              }}
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
          onClick={() => onFavoritesChange(!favoritesOnly)}
          className={cn(
            "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
            favoritesOnly
              ? "bg-primary/20 text-primary"
              : "bg-white/5 text-muted hover:bg-white/10 hover:text-fg",
          )}
          aria-pressed={favoritesOnly}
        >
          ★ Favorites
        </button>
      </div>

      {filtersOpen ? (
        <div className="glass-panel flex flex-wrap items-center gap-3 rounded-xl p-4">
          <Button type="button" onClick={onImportClick}>
            <Upload className="size-4" />
            Import Library
          </Button>
          <p className="text-xs text-muted">
            Press <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono">/</kbd> to
            focus search · <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono">i</kbd> to
            import
          </p>
        </div>
      ) : null}
    </div>
  );
}
