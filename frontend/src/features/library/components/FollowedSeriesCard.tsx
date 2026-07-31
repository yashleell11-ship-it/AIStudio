"use client";

import Image from "next/image";
import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import type { SeriesTracker } from "@/features/updates/types";
import { cn } from "@/lib/cn";
import { type FollowedSeriesMeta, followedSubtitle } from "../followed-meta";
import { trackerCoverUrl, trackerHref } from "../tracker-cover";

/**
 * A cover-first Library card for one followed series.
 *
 * Mirrors `FollowedSeriesCard` on mobile: cover, title, and a single muted
 * meta line — omitted entirely when nothing true is known, rather than
 * claiming "0 chapters".
 */
export function FollowedSeriesCard({
  tracker,
  meta,
}: {
  tracker: SeriesTracker;
  meta: FollowedSeriesMeta;
}) {
  const cover = trackerCoverUrl(tracker);
  const subtitle = followedSubtitle(tracker, meta);

  return (
    <Link
      href={trackerHref(tracker)}
      className="group block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <div className="relative aspect-[2/3] w-full overflow-hidden rounded-xl bg-surface-2">
        {cover ? (
          <Image
            src={cover}
            alt={tracker.series_title}
            fill
            className="object-cover transition-transform duration-300 group-hover:scale-105"
            sizes="(max-width: 640px) 45vw, (max-width: 1024px) 30vw, 200px"
            unoptimized
          />
        ) : null}

        {meta.unreadCount > 0 ? (
          <span className="absolute right-2 top-2 rounded-full bg-primary px-2 py-0.5 text-[0.625rem] font-bold tracking-wide text-primary-fg">
            {meta.unreadCount} NEW
          </span>
        ) : tracker.last_error ? (
          <span
            title="Last update check failed"
            className="absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/70 text-warning backdrop-blur-sm"
          >
            <AlertTriangle className="size-3.5" aria-hidden />
            <span className="sr-only">Last update check failed</span>
          </span>
        ) : null}
      </div>

      <h3 className="mt-2 line-clamp-2 text-sm font-semibold leading-tight text-fg">
        {tracker.series_title}
      </h3>
      {subtitle ? (
        <p className={cn("mt-0.5 truncate text-xs text-muted")}>{subtitle}</p>
      ) : null}
    </Link>
  );
}
