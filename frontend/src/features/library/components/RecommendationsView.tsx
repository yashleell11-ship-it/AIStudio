"use client";

import Link from "next/link";
import { Heart, TriangleAlert, WifiOff } from "lucide-react";
import { useRecommendations } from "@/features/library/hooks";
import { EmptyState } from "@/components/ui/empty-state";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";

/**
 * Source-native recommendations (spec §5.2): with no external catalog there is
 * nothing to recommend beyond the followed set, so the backend returns the top
 * genres across what the profile follows. Each links into a federated browse.
 */
export function RecommendationsView() {
  const recommendationsQuery = useRecommendations(20);
  const genres = recommendationsQuery.data ?? [];
  const viewState = resolveViewState({
    isLoading: recommendationsQuery.isLoading,
    error: recommendationsQuery.error,
    isEmpty: genres.length === 0,
  });

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Recommendations</h1>
          <p className="page-subtitle">
            The genres you read most — tap one to browse more like it.
          </p>
        </div>

        {viewState === "loading" ? (
          <div className="flex flex-wrap gap-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-9 w-28 animate-pulse rounded-full bg-surface-2" />
            ))}
          </div>
        ) : viewState === "offline" ? (
          <EmptyState
            tone="offline"
            icon={WifiOff}
            title="You're offline"
            description="Recommendations need a connection to load. Chapters you've downloaded still open with no connection at all."
            action={{ label: "Go to Downloads", href: "/downloads" }}
          />
        ) : viewState === "error" ? (
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Couldn't load recommendations"
            description={apiErrorMessage(recommendationsQuery.error, "Something went wrong.")}
            action={{ label: "Try again", onClick: () => void recommendationsQuery.refetch() }}
          />
        ) : viewState === "empty" ? (
          <EmptyState
            icon={Heart}
            title="No recommendations yet"
            description="Follow a few series and their genres will show up here."
            action={{ label: "Browse Sources", href: "/sources" }}
          />
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
