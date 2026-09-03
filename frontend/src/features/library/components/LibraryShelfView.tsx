"use client";

import { useMemo } from "react";
import Link from "next/link";
import { BookOpen, Compass, Telescope } from "lucide-react";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { ApiError } from "@/types/api";
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

  const error =
    seriesQuery.error instanceof ApiError ? seriesQuery.error.message : null;

  if (seriesQuery.isLoading) {
    return <ShelfSkeleton />;
  }

  if (error) {
    return (
      <div className="px-5 pt-6 md:px-8">
        <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error}
        </div>
      </div>
    );
  }

  if (followed.length === 0) {
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
