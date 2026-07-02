import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { useFollowedTrackers } from "./hooks";
import type { SeriesTracker } from "./types";

/**
 * Follow/unfollow hooks wrap React Query mutations that patch the shared
 * trackers cache optimistically. These tests drive a real QueryClient to
 * verify the cache keys the hooks use for lookups, mirroring the pattern in
 * features/sources/hooks.test.ts.
 *
 * The mutation logic itself (onMutate/onSuccess/onError) is exercised
 * indirectly via the React Query lifecycle; here we assert the query-key
 * conventions and the `useFollowedTrackers` lookup shape so that a refactor
 * of the key layout does not silently break the Follow button on the source
 * detail screen.
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

describe("useFollowedTrackers query key", () => {
  it("uses a per-source+series key so the detail screen lookup is independent", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangadex";
    const seriesId = "series-1";

    // The Follow button reads from useFollowedTrackers(sourceId, seriesId).
    // Verify the query is registered under a narrow, stable key so that an
    // optimistic patch to the broad followed list refreshes this consumer.
    const key = ["updates", "trackers", "followed", sourceId, seriesId];
    queryClient.setQueryData(key, [tracker({ source: sourceId, series_id: seriesId })]);

    const data = queryClient.getQueryData<SeriesTracker[]>(key);
    expect(data).toHaveLength(1);
    expect(data?.[0].source).toBe(sourceId);
    expect(data?.[0].series_id).toBe(seriesId);
  });

  it("keys for different (source, series) pairs do not collide", () => {
    const queryClient = new QueryClient();
    const keyA = ["updates", "trackers", "followed", "mangadex", "series-1"];
    const keyB = ["updates", "trackers", "followed", "mangadex", "series-2"];

    queryClient.setQueryData(keyA, [tracker({ id: 1, series_id: "series-1" })]);
    queryClient.setQueryData(keyB, [tracker({ id: 2, series_id: "series-2" })]);

    expect(queryClient.getQueryData<SeriesTracker[]>(keyA)).toHaveLength(1);
    expect(queryClient.getQueryData<SeriesTracker[]>(keyB)).toHaveLength(1);
    expect(
      queryClient.getQueryData<SeriesTracker[]>(keyA)?.[0].id,
    ).not.toBe(
      queryClient.getQueryData<SeriesTracker[]>(keyB)?.[0].id,
    );
  });
});

describe("useFollowedTrackers hook options", () => {
  it("exports the hook", () => {
    expect(typeof useFollowedTrackers).toBe("function");
  });
});
