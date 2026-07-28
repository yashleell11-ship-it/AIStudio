"use client";

import {
  DEFAULT_LIBRARY_DENSITY,
  type LibraryDensity,
  densityGridClassName,
} from "@/features/library/density";
import { cn } from "@/lib/cn";
import { SeriesCard, SeriesListItem, type SeriesSelectHandler } from "./SeriesCard";
import type { SeriesSummary } from "../types";

export type SeriesGridEmptyState = "library" | "search" | "filter";

export interface SeriesGridSelection {
  selecting: boolean;
  selectedIds: ReadonlySet<number>;
  onSelect: SeriesSelectHandler;
}

interface SeriesGridProps {
  items: SeriesSummary[];
  isLoading?: boolean;
  emptyState?: SeriesGridEmptyState;
  density?: LibraryDensity;
  /** Omitted by callers that have no multi-select (collections, for now). */
  selection?: SeriesGridSelection;
}

function emptyCopy(state: SeriesGridEmptyState): { title: string; description: string } {
  switch (state) {
    case "search":
      return {
        title: "No results found",
        description: "Try a different search term or clear filters.",
      };
    case "filter":
      return {
        title: "No series match these filters",
        description: "Adjust your filters or favorites toggle to see more series.",
      };
    default:
      return {
        title: "Your library is empty",
        description:
          "Import a folder containing your manhwa, manga, or manhua collection to get started.",
      };
  }
}

/** Skeleton count scaled to the density, so the placeholder fills the same space. */
function skeletonCount(density: LibraryDensity): number {
  switch (density) {
    case "compact":
      return 24;
    case "list":
      return 8;
    default:
      return 12;
  }
}

export function SeriesGrid({
  items,
  isLoading,
  emptyState = "library",
  density = DEFAULT_LIBRARY_DENSITY,
  selection,
}: SeriesGridProps) {
  if (isLoading) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading library"
        className={densityGridClassName(density)}
      >
        {Array.from({ length: skeletonCount(density) }).map((_, index) => (
          <div
            key={index}
            className={cn(
              "animate-pulse rounded-2xl bg-surface-2",
              density === "list" ? "h-20" : "aspect-[2/3]",
            )}
          />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    const copy = emptyCopy(emptyState);
    return (
      <div className="glass-panel rounded-3xl border border-dashed border-border/50 p-12 text-center">
        <p className="text-lg font-medium text-fg">{copy.title}</p>
        <p className="mt-2 text-sm text-muted">{copy.description}</p>
      </div>
    );
  }

  const cardSelection = (series: SeriesSummary) =>
    selection
      ? {
          selecting: selection.selecting,
          selected: selection.selectedIds.has(series.id),
          onSelect: selection.onSelect,
        }
      : undefined;

  return (
    <div
      className={cn(
        densityGridClassName(density),
        // Shift-click drags the browser's own text selection across every card
        // it passes, which looks like a bug and hides the highlight.
        selection?.selecting && "select-none",
      )}
    >
      {items.map((series) =>
        density === "list" ? (
          <SeriesListItem
            key={series.id}
            series={series}
            selection={cardSelection(series)}
          />
        ) : (
          <SeriesCard
            key={series.id}
            series={series}
            density={density}
            selection={cardSelection(series)}
          />
        ),
      )}
    </div>
  );
}
