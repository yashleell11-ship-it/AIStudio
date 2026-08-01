"use client";

import { useMemo } from "react";
import Link from "next/link";
import { BookOpen, Compass, Telescope } from "lucide-react";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { useTrackers, useUpdateNotifications } from "@/features/updates/hooks";
import type { SeriesTracker } from "@/features/updates/types";
import { ApiError } from "@/types/api";
import { followedSeriesMeta } from "../followed-meta";
import { FollowedSeriesCard } from "./FollowedSeriesCard";

/**
 * The Library tab — the followed series, and nothing else.
 *
 * Deliberately spare (DESIGN_SYSTEM.md hard constraint: "Library tab (mobile)
 * = followed series only"): one heading, one grid of covers. This is the web
 * mirror of `DashboardScreen` on mobile, and it replaced a cinematic marketing
 * home page that showed a hero, a cover marquee, an "about" pitch and a sticky
 * card stack — none of which is what someone opening their own reader wants to
 * land on.
 *
 * Browse Sources is reachable from exactly one place at a time: the empty state
 * when there is nothing followed yet, otherwise the small header action. Two
 * routes to the same destination on one screen is noise.
 */
export function LibraryShelfView() {
  const trackersQuery = useTrackers();
  const notificationsQuery = useUpdateNotifications();

  // Library = followed only; downloaded-only trackers never appear here.
  const followed = useMemo<SeriesTracker[]>(
    () => (trackersQuery.data ?? []).filter((t) => t.track_kind === "followed"),
    [trackersQuery.data],
  );

  const notifications = useMemo(
    () => notificationsQuery.data ?? [],
    [notificationsQuery.data],
  );

  const error =
    trackersQuery.error instanceof ApiError ? trackersQuery.error.message : null;

  if (trackersQuery.isLoading) {
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
        {followed.map((tracker) => (
          <FollowedSeriesCard
            key={tracker.id}
            tracker={tracker}
            meta={followedSeriesMeta(tracker, notifications)}
          />
        ))}
      </div>
    </div>
  );
}

/**
 * Empty shelf — every account on this server starts here, so it has to say what
 * to do and offer the one way to do it.
 */
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
