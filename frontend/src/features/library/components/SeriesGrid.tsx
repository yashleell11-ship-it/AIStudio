"use client";

import { Compass, Library, SearchX, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { EmptyState, type EmptyStateAction } from "@/components/ui/empty-state";
import {
  DEFAULT_LIBRARY_DENSITY,
  type LibraryDensity,
  densityGridClassName,
} from "@/features/library/density";
import { cn } from "@/lib/cn";
import { SeriesCard, SeriesListItem, type SeriesSelectHandler } from "./SeriesCard";
import type { FollowedSeries } from "../types";

export type SeriesGridEmptyState = "library" | "search" | "filter";

export interface SeriesGridSelection {
  selecting: boolean;
  selectedIds: ReadonlySet<number>;
  onSelect: SeriesSelectHandler;
}

interface SeriesGridProps {
  items: FollowedSeries[];
  isLoading?: boolean;
  emptyState?: SeriesGridEmptyState;
  density?: LibraryDensity;
  /** Omitted by callers that have no multi-select (collections, for now). */
  selection?: SeriesGridSelection;
}

function emptyCopy(state: SeriesGridEmptyState): {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: EmptyStateAction;
} {
  switch (state) {
    case "search":
      return {
        icon: SearchX,
        title: "No results found",
        description: "Try a different search term or clear filters.",
      };
    case "filter":
      return {
        icon: SlidersHorizontal,
        title: "No series match these filters",
        description: "Adjust your filters or favorites toggle to see more series.",
      };
    default:
      return {
        icon: Library,
        title: "Nothing followed yet",
        description:
          "This account has no series yet. Browse a source and follow one to start your library.",
        action: { label: "Browse Sources", href: "/sources", icon: Compass },
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
      <EmptyState
        icon={copy.icon}
        title={copy.title}
        description={copy.description}
        action={copy.action}
      />
    );
  }

  const cardSelection = (series: FollowedSeries) =>
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
