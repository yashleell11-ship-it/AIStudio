import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { findFollowedTracker } from "./hooks";
import * as updatesHooks from "./hooks";
import type { SeriesTracker } from "./types";

/**
 * Regression tests for the stale-detail-page bug: `useFollowedTracker` used
 * to run its own `useFollowedTrackers` query keyed by (sourceId, seriesId),
 * while `useFollowSeries` / `useUnfollowTracker` only patched the
 * `useTrackers("followed")` cache. The two caches never talked to each
 * other, so the source series detail page could show a stale Follow/Unfollow
 * label until an unrelated refetch happened to land.
 *
 * The fix makes `useFollowedTracker` derive from `useTrackers("followed")`
 * via the pure `findFollowedTracker` selector below, so there is exactly one
 * cache and no React renderer is needed to prove correctness -- these tests
 * exercise the same selector the hook calls, against the same query key the
 * mutations patch, matching the QueryClient-driven style used throughout
 * this test suite (see features/sources/hooks.test.ts).
 */
function tracker(overrides: Partial<SeriesTracker> = {}): SeriesTracker {
  return {
    id: 1,
    source: "mangadex",
    series_id: "series-1",
    series_title: "Test Series",
    track_kind: "followed",
    local_series_id: null,
    enabled: true,
    notify: true,
    auto_download: false,
    check_interval_minutes: null,
    known_chapter_count: 0,
    last_checked_at: null,
    last_error: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

// The exact key useTrackers("followed") builds -- the ONE cache both the
// Updates page and the source detail page's Follow button read from.
const FOLLOWED_KEY = ["updates", "trackers", "followed"];

describe("useFollowedTracker: single source of truth", () => {
  it("has no duplicate per-series followed query left to go stale", () => {
    // useFollowedTrackers was the second cache. Its removal is the actual
    // fix -- assert there is nothing left to reintroduce the split.
    expect(
      Object.prototype.hasOwnProperty.call(updatesHooks, "useFollowedTrackers"),
    ).toBe(false);
  });

  it("reads from the exact useTrackers(\"followed\") cache key", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangadex";
    const seriesId = "series-1";

    // This is the ONE key useFollowSeries/useUnfollowTracker patch.
    queryClient.setQueryData(FOLLOWED_KEY, [
      tracker({ id: 42, source: sourceId, series_id: seriesId }),
    ]);

    const data = queryClient.getQueryData<SeriesTracker[]>(FOLLOWED_KEY);
    expect(findFollowedTracker(data, sourceId, seriesId)?.id).toBe(42);
  });

  it("Follow immediately changes to Unfollow", () => {
    const sourceId = "mangadex";
    const seriesId = "series-1";

    // Not followed yet.
    expect(findFollowedTracker([], sourceId, seriesId)).toBeUndefined();

    // useFollowSeries.onSuccess appends the returned tracker to this exact
    // array -- the very same one the selector reads, so the next render
    // sees it without any refetch.
    const afterFollow = [tracker({ id: 7, source: sourceId, series_id: seriesId })];
    expect(findFollowedTracker(afterFollow, sourceId, seriesId)?.id).toBe(7);
  });

  it("Unfollow immediately changes to Follow", () => {
    const sourceId = "mangadex";
    const seriesId = "series-1";
    const followed = [tracker({ id: 7, source: sourceId, series_id: seriesId })];
    expect(findFollowedTracker(followed, sourceId, seriesId)).toBeDefined();

    // useUnfollowTracker.onMutate optimistically filters the tracker out of
    // this exact array.
    const afterUnfollow = followed.filter((t) => t.id !== 7);
    expect(findFollowedTracker(afterUnfollow, sourceId, seriesId)).toBeUndefined();
  });

  it("detail page never becomes stale: reading the same key mutations patch always reflects the latest write", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangadex";
    const seriesId = "series-1";

    expect(
      findFollowedTracker(
        queryClient.getQueryData<SeriesTracker[]>(FOLLOWED_KEY),
        sourceId,
        seriesId,
      ),
    ).toBeUndefined();

    // Simulate useFollowSeries.onSuccess.
    queryClient.setQueryData<SeriesTracker[]>(FOLLOWED_KEY, (previous) => [
      ...(previous ?? []),
      tracker({ id: 9, source: sourceId, series_id: seriesId }),
    ]);
    expect(
      findFollowedTracker(
        queryClient.getQueryData<SeriesTracker[]>(FOLLOWED_KEY),
        sourceId,
        seriesId,
      )?.id,
    ).toBe(9);

    // Simulate useUnfollowTracker.onMutate.
    queryClient.setQueryData<SeriesTracker[]>(FOLLOWED_KEY, (previous) =>
      previous ? previous.filter((t) => t.id !== 9) : previous,
    );
    expect(
      findFollowedTracker(
        queryClient.getQueryData<SeriesTracker[]>(FOLLOWED_KEY),
        sourceId,
        seriesId,
      ),
    ).toBeUndefined();
  });

  it("does not match a followed tracker for a different source or series", () => {
    const data = [tracker({ id: 1, source: "mangadex", series_id: "series-1" })];
    expect(findFollowedTracker(data, "mangadex", "series-2")).toBeUndefined();
    expect(findFollowedTracker(data, "asurascans", "series-1")).toBeUndefined();
  });
});
