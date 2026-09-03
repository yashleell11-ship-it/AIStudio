"use client";

import Link from "next/link";
import { useRecommendations } from "@/features/library/hooks";
import { ApiError } from "@/types/api";

/**
 * Source-native recommendations (spec §5.2): with no external catalog there is
 * nothing to recommend beyond the followed set, so the backend returns the top
 * genres across what the profile follows. Each links into a federated browse.
 */
export function RecommendationsView() {
  const recommendationsQuery = useRecommendations(20);
  const genres = recommendationsQuery.data ?? [];

  const errorMessage =
    recommendationsQuery.error instanceof ApiError
      ? recommendationsQuery.error.message
      : recommendationsQuery.error
        ? "Failed to load recommendations."
        : null;

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Recommendations</h1>
          <p className="page-subtitle">
            The genres you read most — tap one to browse more like it.
          </p>
        </div>

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        {recommendationsQuery.isLoading ? (
          <div className="flex flex-wrap gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-9 w-28 animate-pulse rounded-full bg-surface-2" />
            ))}
          </div>
        ) : genres.length === 0 ? (
          <div className="empty-state">
            <p className="text-lg font-medium text-fg">No recommendations yet</p>
            <p className="mt-2 text-sm text-muted">
              Follow a few series and their genres will show up here.
            </p>
            <Link
              href="/sources"
              className="mt-4 inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-fg hover:bg-primary-hover"
            >
              Browse Sources
            </Link>
          </div>
        ) : (
          <div className="flex flex-wrap gap-3">
            {genres.map((entry) => (
              <Link
                key={entry.genre}
                href={`/search?q=${encodeURIComponent(entry.genre)}`}
                className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/[0.03] px-4 py-2 text-sm text-fg transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
              >
                <span className="capitalize">{entry.genre}</span>
                <span className="rounded-full bg-white/10 px-1.5 text-xs tabular-nums text-muted">
                  {entry.weight}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
