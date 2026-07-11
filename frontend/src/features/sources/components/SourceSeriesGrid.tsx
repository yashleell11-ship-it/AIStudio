"use client";

import { SourceSeriesCard } from "./SourceSeriesCard";
import type { SourceSeriesSummary } from "../types";

interface SourceSeriesGridProps {
  sourceId: string;
  items: SourceSeriesSummary[];
  isLoading?: boolean;
  query?: string;
  errorMessage?: string;
}

export function SourceSeriesGrid({
  sourceId,
  items,
  isLoading,
  query,
  errorMessage,
}: SourceSeriesGridProps) {
  if (errorMessage) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface p-12 text-center">
        <p className="text-lg font-medium text-fg">Could not load source catalog</p>
        <p className="mt-2 text-sm text-muted">{errorMessage}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
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
    return (
      <div className="rounded-xl border border-dashed border-border bg-surface p-12 text-center">
        <p className="text-lg font-medium text-fg">No series found</p>
        <p className="mt-2 text-sm text-muted">
          {query
            ? `No results for "${query}" on this source.`
            : "This source returned no series."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {items.map((series) => (
        <SourceSeriesCard key={series.id} sourceId={sourceId} series={series} />
      ))}
    </div>
  );
}
