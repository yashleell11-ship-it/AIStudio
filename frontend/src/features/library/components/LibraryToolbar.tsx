"use client";

import { useCallback, useRef, useState } from "react";
import {
  CheckSquare,
  Grid3X3,
  LayoutGrid,
  LayoutList,
  Search,
  SlidersHorizontal,
  Upload,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import {
  DENSITY_LABELS,
  type LibraryDensity,
} from "@/features/library/density";
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
  /** Discrete controls push history; only the search box replaces it. */
  onQueryChange: (next: LibraryQuery) => void;
  searchInput: string;
  onSearchInputChange: (value: string) => void;
  density: LibraryDensity;
  onDensityChange: (density: LibraryDensity) => void;
  selecting: boolean;
  onSelectingChange: (selecting: boolean) => void;
  onImportClick: () => void;
  seriesCount: number;
  tags: Tag[];
}

const FILTER_CHIPS: { value: SeriesFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "reading", label: "Reading" },
  { value: "unread", label: "Not Started" },
];

const SORT_OPTIONS: { value: SeriesSort; label: string }[] = [
  { value: "updated", label: "Recently Updated" },
  { value: "date_added", label: "Recently Added" },
  { value: "sort_title", label: "Title" },
  { value: "recent", label: "Recently Read" },
  { value: "author", label: "Author" },
  { value: "year", label: "Year" },
  { value: "total_chapters", label: "Total Chapters" },
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
};

/**
 * A filter that has no control of its own but is set in the URL — a deep link
 * from a collection, a language, "only series with chapters". Rendered as a
 * removable chip so it is visible and reversible instead of silently narrowing
 * the grid.
 */
function ActiveParamChip({
  label,
  onClear,
}: {
  label: string;
  onClear: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs text-primary">
      {label}
      <button
        type="button"
        onClick={onClear}
        aria-label={`Clear ${label} filter`}
        className="rounded-full p-0.5 transition-colors hover:bg-primary/20"
      >
        <X className="size-3" aria-hidden />
      </button>
    </span>
  );
}

export function LibraryToolbar({
  query,
  onQueryChange,
  searchInput,
  onSearchInputChange,
  density,
  onDensityChange,
  selecting,
  onSelectingChange,
  onImportClick,
  seriesCount,
  tags,
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

  const patch = useCallback(
    (changes: Partial<LibraryQuery>) => onQueryChange({ ...query, ...changes }),
    [onQueryChange, query],
  );

  const selectedTag = tags.find((tag) => tag.id === query.tag_id) ?? null;
  const filtersActive = hasActiveFilters(query);

  return (
    <div className="mb-6 space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <HeroHeading className="text-[clamp(1.75rem,9vw,2.75rem)] leading-none md:text-6xl">
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
          placeholder="Search by title, author, or tag..."
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

        {query.language ? (
          <ActiveParamChip
            label={`Language: ${query.language}`}
            onClear={() => patch({ language: null })}
          />
        ) : null}
        {query.has_chapters !== null ? (
          <ActiveParamChip
            label={query.has_chapters ? "Has chapters" : "No chapters"}
            onClear={() => patch({ has_chapters: null })}
          />
        ) : null}
        {query.collection_id !== null ? (
          <ActiveParamChip
            label={`Collection #${query.collection_id}`}
            onClear={() => patch({ collection_id: null })}
          />
        ) : null}
        {query.library_id !== null ? (
          <ActiveParamChip
            label={`Library #${query.library_id}`}
            onClear={() => patch({ library_id: null })}
          />
        ) : null}
        {selectedTag ? (
          <ActiveParamChip
            label={`Tag: ${selectedTag.name}`}
            onClear={() => patch({ tag_id: null })}
          />
        ) : null}
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

          <label className="flex flex-col gap-1 text-xs text-muted">
            Tag
            <select
              value={query.tag_id ?? ""}
              onChange={(event) =>
                patch({ tag_id: event.target.value ? Number(event.target.value) : null })
              }
              className="h-9 rounded-lg border border-border/50 bg-white/5 px-3 text-sm text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
            >
              <option value="">Any</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
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
                  // The search box is not a filter chip; clearing filters must
                  // not also throw away what the user typed.
                  search: query.search,
                  sort: query.sort,
                })
              }
            >
              Clear filters
            </Button>
          ) : null}

          <Button type="button" onClick={onImportClick}>
            <Upload className="size-4" />
            Import Library
          </Button>

          <p className="w-full text-xs text-muted">
            Press <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono">/</kbd> to
            focus search · <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono">i</kbd> to
            import · shift-click a cover to select a range
          </p>
        </div>
      ) : null}
    </div>
  );
}
