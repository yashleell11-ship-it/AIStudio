import { describe, expect, it } from "vitest";
import type { SeriesTracker } from "@/features/updates/types";
import { resolveFollowControlState, resolveSeriesFollowLink } from "./follow-link";
import type { SeriesDetail } from "./types";

/**
 * The Follow control on the LOCAL series page: whether it renders at all, and
 * what it says on first paint.
 *
 * The bug it exists for: Follow lived only on the source-browse page, so the
 * series reached from a downloaded chapter — the one the owner cared enough to
 * download — could not be followed and got no update checks or new-chapter
 * notifications. Both decisions are pure functions of the detail payload plus
 * the followed-trackers cache, so they are testable without a renderer (the
 * suite has no DOM testing library; same style as updates/hooks.test.ts).
 */
function detail(overrides: Partial<SeriesDetail> = {}): SeriesDetail {
  return {
    id: 7,
    library_id: 1,
    title: "Solo Leveling",
    sort_title: "solo leveling",
    original_title: null,
    author: null,
    artist: null,
    description: null,
    status: null,
    content_rating: "safe",
    language: "ko",
    year: null,
    cover_path: null,
    folder_path: "/library/solo-leveling",
    is_favorite: false,
    reading_status: "reading",
    chapter_count: 3,
    read_chapters: 1,
    page_count: 60,
    total_chapters: 3,
    total_pages: 60,
    first_chapter_id: 11,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    reading_progress: null,
    in_library: true,
    chapters: [],
    tags: [],
    collections: [],
    ...overrides,
  };
}

function tracker(overrides: Partial<SeriesTracker> = {}): SeriesTracker {
  return {
    id: 42,
    source: "mangadex",
    series_id: "sl-1",
    series_title: "Solo Leveling",
    track_kind: "followed",
    local_series_id: 7,
    enabled: true,
    notify: true,
    auto_download: false,
    check_interval_minutes: null,
    known_chapter_count: 3,
    last_checked_at: null,
    last_error: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

describe("resolveSeriesFollowLink", () => {
  it("offers no control for a hand-imported folder with no origin", () => {
    // `GET /library/series/{id}` states both ids as null here. There is nothing
    // to track, so the control is omitted rather than rendered disabled.
    expect(
      resolveSeriesFollowLink(detail({ source_id: null, source_series_id: null })),
    ).toBeNull();
  });

  it("offers no control when the payload predates the source-link fields", () => {
    // Absent, not null: the same interface is reused for responses that do not
    // carry these fields, and undefined must not read as a followable link.
    expect(resolveSeriesFollowLink(detail())).toBeNull();
  });

  it("offers no control while the series itself is still loading", () => {
    expect(resolveSeriesFollowLink(undefined)).toBeNull();
    expect(resolveSeriesFollowLink(null)).toBeNull();
  });

  it("offers no control for half a link, which could not be followed anyway", () => {
    // The backend sets both or neither; a half link would 422 on
    // POST /updates/trackers/follow, and a button that always fails is worse
    // than no button.
    expect(
      resolveSeriesFollowLink(detail({ source_id: "mangadex", source_series_id: null })),
    ).toBeNull();
    expect(
      resolveSeriesFollowLink(detail({ source_id: null, source_series_id: "sl-1" })),
    ).toBeNull();
    // Empty strings are equally unusable as ids.
    expect(
      resolveSeriesFollowLink(detail({ source_id: "", source_series_id: "sl-1" })),
    ).toBeNull();
  });

  it("carries the origin for a downloaded series that is not followed", () => {
    expect(
      resolveSeriesFollowLink(
        detail({
          source_id: "mangadex",
          source_series_id: "sl-1",
          is_followed: false,
          follow_tracker_id: null,
        }),
      ),
    ).toEqual({
      sourceId: "mangadex",
      sourceSeriesId: "sl-1",
      seedIsFollowed: false,
      seedTrackerId: null,
    });
  });

  it("seeds the followed state and its tracker id from the payload", () => {
    expect(
      resolveSeriesFollowLink(
        detail({
          source_id: "mangadex",
          source_series_id: "sl-1",
          is_followed: true,
          follow_tracker_id: 42,
        }),
      ),
    ).toEqual({
      sourceId: "mangadex",
      sourceSeriesId: "sl-1",
      seedIsFollowed: true,
      seedTrackerId: 42,
    });
  });

  it("falls back to Follow when a followed payload has no tracker id", () => {
    // Contradictory, and the direction matters: Unfollow is
    // DELETE /updates/trackers/{id} and there would be no id to send, whereas
    // re-following an already-followed series returns the existing tracker.
    expect(
      resolveSeriesFollowLink(
        detail({
          source_id: "mangadex",
          source_series_id: "sl-1",
          is_followed: true,
          follow_tracker_id: null,
        }),
      ),
    ).toMatchObject({ seedIsFollowed: false, seedTrackerId: null });
  });

  it("ignores a tracker id left on a payload that is not followed", () => {
    expect(
      resolveSeriesFollowLink(
        detail({
          source_id: "mangadex",
          source_series_id: "sl-1",
          is_followed: false,
          follow_tracker_id: 42,
        }),
      ),
    ).toMatchObject({ seedIsFollowed: false, seedTrackerId: null });
  });
});

describe("resolveFollowControlState", () => {
  const followedLink = {
    sourceId: "mangadex",
    sourceSeriesId: "sl-1",
    seedIsFollowed: true,
    seedTrackerId: 42,
  };
  const unfollowedLink = {
    sourceId: "mangadex",
    sourceSeriesId: "sl-1",
    seedIsFollowed: false,
    seedTrackerId: null,
  };

  it("shows Unfollow on first paint, before the tracker list arrives", () => {
    // The flash this exists to prevent: an already-followed series rendering
    // "Follow" until GET /updates/trackers resolves.
    expect(resolveFollowControlState(followedLink, undefined, false)).toEqual({
      isFollowed: true,
      trackerId: 42,
    });
  });

  it("keeps the payload's answer when the tracker list never loads", () => {
    // A failed or offline tracker request must not downgrade a real server
    // answer to "not followed".
    expect(resolveFollowControlState(followedLink, undefined, false).isFollowed).toBe(
      true,
    );
  });

  it("lets the loaded tracker list overrule a stale not-followed payload", () => {
    // Followed from the source page in another tab: the tracker cache knows,
    // this payload does not.
    expect(resolveFollowControlState(unfollowedLink, tracker({ id: 99 }), true)).toEqual({
      isFollowed: true,
      trackerId: 99,
    });
  });

  it("lets the loaded tracker list overrule a stale followed payload", () => {
    // The unfollow case: the mutation drops the row optimistically, so the
    // button must flip on click rather than waiting for the detail refetch.
    expect(resolveFollowControlState(followedLink, undefined, true)).toEqual({
      isFollowed: false,
      trackerId: null,
    });
  });

  it("prefers the live tracker id over the payload's", () => {
    // Unfollow then re-follow mints a new tracker row; deleting the old id
    // would 404.
    expect(
      resolveFollowControlState(followedLink, tracker({ id: 77 }), true).trackerId,
    ).toBe(77);
  });

  it("reports an unfollowed series as unfollowed either way", () => {
    expect(resolveFollowControlState(unfollowedLink, undefined, false)).toEqual({
      isFollowed: false,
      trackerId: null,
    });
    expect(resolveFollowControlState(unfollowedLink, undefined, true)).toEqual({
      isFollowed: false,
      trackerId: null,
    });
  });
});
