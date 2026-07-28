"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Bell, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useFollowSeries,
  useFollowedTracker,
  useTrackers,
  useUnfollowTracker,
} from "@/features/updates/hooks";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import { resolveFollowControlState, type SeriesFollowLink } from "../follow-link";
import { seriesQueryKey } from "../hooks";

interface SeriesFollowButtonProps {
  /** Local series id — what the detail payload this state came from is keyed by. */
  seriesId: number;
  /** Title stored on the tracker, and shown on the Updates page. */
  seriesTitle: string;
  /** Origin + seed state from {@link resolveSeriesFollowLink}; never null. */
  link: SeriesFollowLink;
  className?: string;
}

/**
 * Follow/Unfollow for a series on the LOCAL library page.
 *
 * The whole point of the four source-link fields: a downloaded series is
 * reached from its downloaded chapters, not from source browse, so until now
 * the only page that offered Follow was the one the owner never went back to.
 * A series he downloaded got no update checks and no new-chapter notifications.
 *
 * Rendered only when the series has an origin — the caller resolves that and
 * omits this component otherwise, so there is no disabled-and-unexplained
 * state here to reason about.
 *
 * Follow state is per (user, profile). No per-profile cache handling is needed
 * here: `ProfileCacheBoundary` (app/providers.tsx:96) drops every query root
 * except `auth`/`profiles` on a switch, so both the tracker list and the series
 * payload this reads are refetched for the profile that arrives.
 */
export function SeriesFollowButton({
  seriesId,
  seriesTitle,
  link,
  className,
}: SeriesFollowButtonProps) {
  const queryClient = useQueryClient();
  // Two reads of ONE query (`["updates","trackers","followed"]`, deduped by
  // react-query, no extra request): the hook finds this series' row, while the
  // query itself says whether the list has loaded at all. Without the second,
  // "not in the list" and "list not here yet" are indistinguishable and the
  // button flashes Follow on an already-followed series.
  const followedTrackers = useTrackers("followed");
  const tracker = useFollowedTracker(link.sourceId, link.sourceSeriesId);
  const followMutation = useFollowSeries();
  const unfollowMutation = useUnfollowTracker();
  const [error, setError] = useState<string | null>(null);

  const { isFollowed, trackerId } = resolveFollowControlState(
    link,
    tracker,
    followedTrackers.data !== undefined,
  );
  const busy = followMutation.isPending || unfollowMutation.isPending;

  const toggle = async () => {
    setError(null);
    try {
      if (isFollowed && trackerId !== null) {
        await unfollowMutation.mutateAsync(trackerId);
      } else {
        await followMutation.mutateAsync({
          // The tracker API names these `source`/`series_id`, not the
          // `source_id`/`source_series_id` the series payload uses.
          source: link.sourceId,
          series_id: link.sourceSeriesId,
          series_title: seriesTitle,
          // A local series payload carries the owner's own `tags`, not the
          // source's genres, so there is no adult-rating signal to forward.
          // Empty says exactly that; inventing one from local tags would not.
          genres: [],
        });
      }
      // Follow/unfollow itself is already reflected everywhere the Updates page
      // and the source page look: both mutations patch the followed-trackers
      // cache directly. This payload is the one thing they do not touch — its
      // `is_followed`/`follow_tracker_id` are now stale, and a reload (or any
      // remount that refetches) would otherwise resurrect the old answer as the
      // first-paint seed.
      // Not awaited: the button already reads the patched tracker cache, and a
      // refetch that fails must not surface as "your follow failed".
      void queryClient.invalidateQueries({ queryKey: seriesQueryKey(seriesId) });
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Failed to update follow status.",
      );
    }
  };

  const label = isFollowed ? `Unfollow ${seriesTitle}` : `Follow ${seriesTitle}`;
  const Icon = isFollowed ? BellRing : Bell;

  return (
    <div className={cn("flex flex-col items-start gap-1", className)}>
      {/* Styled as the sibling Favorite toggle, not as a second call to action:
          this cluster already has one primary (Add to library) and the page has
          another in Continue Reading. */}
      <Button
        variant={isFollowed ? "primary" : "secondary"}
        disabled={busy}
        onClick={() => void toggle()}
        aria-label={label}
        title={
          isFollowed
            ? "Stop checking this series for new chapters"
            : "Check this series for new chapters and notify me"
        }
        className={cn(
          "rounded-full",
          isFollowed
            ? "bg-primary/20 text-primary hover:bg-primary/30"
            : "border border-border/50 bg-white/5 hover:bg-white/10",
        )}
      >
        <Icon className={cn("size-4", isFollowed && "fill-primary/20")} aria-hidden />
        {/* The in-flight label comes from WHICH mutation is running, not from
            `isFollowed`: unfollow removes the row optimistically, so by the
            time it is pending `isFollowed` has already flipped to false and
            reading it here would say "Following…" during an unfollow. */}
        {unfollowMutation.isPending
          ? "Unfollowing…"
          : followMutation.isPending
            ? "Following…"
            : isFollowed
              ? "Following"
              : "Follow"}
      </Button>
      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </div>
  );
}
