"use client";

import Link from "next/link";
import { useRecommendations } from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { SeriesCard } from "./SeriesCard";

export function RecommendationsView() {
  const recommendationsQuery = useRecommendations(12);

  const errorMessage =
    recommendationsQuery.error instanceof ApiError
      ? recommendationsQuery.error.message
      : recommendationsQuery.error
        ? "Failed to load recommendations."
        : null;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-fg">Recommendations</h1>
        <p className="mt-1 text-sm text-muted">
          Based on your reading history, tags, and authors.
        </p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {errorMessage}
        </div>
      )}

      {recommendationsQuery.isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      ) : recommendationsQuery.data && recommendationsQuery.data.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border bg-surface p-12 text-center">
          <p className="text-lg font-medium text-fg">No recommendations yet</p>
          <p className="mt-2 text-sm text-muted">
            Start reading some series to get personalized recommendations.
          </p>
          <Link
            href="/library"
            className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg hover:bg-primary-hover"
          >
            Browse Library
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {recommendationsQuery.data?.map((series) => (
            <SeriesCard key={series.id} series={series} />
          ))}
        </div>
      )}
    </div>
  );
}
