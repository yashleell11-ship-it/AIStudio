"use client";

import { useMemo } from "react";
import Link from "next/link";
import { BookOpen, Compass, Telescope, TriangleAlert } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { useSeriesList } from "../hooks";
import { FollowedSeriesCard } from "./FollowedSeriesCard";

/**
 * The Library tab — the followed series, and nothing else (spec §3.4).
 *
 * Source-native: reads `GET /library/series`, the per-profile `followed_series`
 * set. One heading, one grid of covers. Browse Sources is the single call to
 * action, in the empty state or the small header button.
 */
export function LibraryShelfView() {
  const seriesQuery = useSeriesList({
    page: 1,
    per_page: 200,
    sort: "recently_updated",
  });

  const followed = useMemo(
    () => seriesQuery.data?.items ?? [],
    [seriesQuery.data],
  );

  const viewState = resolveViewState({
    isLoading: seriesQuery.isLoading,
    error: seriesQuery.error,
    isEmpty: followed.length === 0,
  });

  if (viewState === "loading") {
    return <ShelfSkeleton />;
  }

  if (viewState === "offline") {
    return (
      <div className="px-5 pt-6 md:px-8">
        <OfflineState
          reason="Your library needs a connection to load."
          onRetry={() => void seriesQuery.refetch()}
        />
      </div>
    );
  }

  if (viewState === "error") {
    return (
      <div className="px-5 pt-6 md:px-8">
        <EmptyState
          tone="error"
          icon={TriangleAlert}
          title="Couldn't load your library"
          description={apiErrorMessage(seriesQuery.error, "Something went wrong.")}
          action={{ label: "Try again", onClick: () => void seriesQuery.refetch() }}
        />
      </div>
    );
  }

  if (viewState === "empty") {
    return <ShelfEmpty />;
  }

  return (
    <div className="px-5 pb-8 pt-6 md:px-8">
      <FadeIn>
        <div className="flex items-start justify-between gap-4">
          <div>
            <HeroHeading className="text-[clamp(1.5rem,6.5vw,3rem)]">Library</HeroHeading>
            <p className="mt-1 text-xs text-muted">
              {followed.length === 1
                ? "1 series followed"
                : `${followed.length} series followed`}
            </p>
          </div>
          <Link
            href="/sources"
            title="Browse Sources"
            className="flex size-11 shrink-0 items-center justify-center rounded-full text-muted transition-colors hover:bg-fg/10 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <Telescope className="size-5" aria-hidden />
            <span className="sr-only">Browse Sources</span>
          </Link>
        </div>
      </FadeIn>

      <div className="mt-6 grid grid-cols-3 gap-x-3 gap-y-5 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
        {followed.map((series) => (
          <FollowedSeriesCard key={series.id} series={series} />
        ))}
      </div>
    </div>
  );
}

function ShelfEmpty() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <BookOpen className="size-10 text-muted" aria-hidden />
      <h1 className="mt-4 font-display text-2xl font-bold text-fg">
        Your library is empty
      </h1>
      <p className="mt-2 max-w-xs text-sm text-muted">
        Follow series from Sources to build your warm little shelf.
      </p>
      <PrimaryPillButton
        href="/sources"
        label="Browse Sources"
        icon={<Compass className="size-4" aria-hidden />}
        className="mt-6"
      />
    </div>
  );
}

function ShelfSkeleton() {
  return (
    <div className="px-5 pb-8 pt-6 md:px-8">
      <div className="h-10 w-40 animate-pulse rounded-lg bg-surface-2" />
      <div className="mt-6 grid grid-cols-3 gap-x-3 gap-y-5 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i}>
            <div className="aspect-[2/3] w-full animate-pulse rounded-xl bg-surface-2" />
            <div className="mt-2 h-3 w-3/4 animate-pulse rounded bg-surface-2" />
          </div>
        ))}
      </div>
    </div>
  );
}
