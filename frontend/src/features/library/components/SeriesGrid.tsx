"use client";

import { SeriesCard, SeriesListItem } from "./SeriesCard";
import type { LibraryViewMode } from "./LibraryToolbar";
import type { SeriesSummary } from "../types";

export type SeriesGridEmptyState = "library" | "search" | "filter";

interface SeriesGridProps {
  items: SeriesSummary[];
  isLoading?: boolean;
  emptyState?: SeriesGridEmptyState;
  viewMode?: LibraryViewMode;
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

export function SeriesGrid({
  items,
  isLoading,
  emptyState = "library",
  viewMode = "grid",
}: SeriesGridProps) {
  if (isLoading) {
    if (viewMode === "list") {
      return (
        <div aria-busy="true" aria-label="Loading library" className="space-y-3">
          {Array.from({ length: 8 }).map((_, index) => (
            <div key={index} className="h-20 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      );
    }

    return (
      <div
        aria-busy="true"
        aria-label="Loading library"
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6"
      >
        {Array.from({ length: 12 }).map((_, index) => (
          <div
            key={index}
            className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2"
          />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    const copy = emptyCopy(emptyState);
    return (
      <div className="glass-panel rounded-xl border border-dashed border-border/50 p-12 text-center">
        <p className="text-lg font-medium text-fg">{copy.title}</p>
        <p className="mt-2 text-sm text-muted">{copy.description}</p>
      </div>
    );
  }

  if (viewMode === "list") {
    return (
      <div className="space-y-3">
        {items.map((series) => (
          <SeriesListItem key={series.id} series={series} />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {items.map((series) => (
        <SeriesCard key={series.id} series={series} />
      ))}
    </div>
  );
}
