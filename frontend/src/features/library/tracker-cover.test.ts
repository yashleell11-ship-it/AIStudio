import { describe, expect, it } from "vitest";
import type { SeriesTracker } from "@/features/updates/types";
import { trackerCoverUrl, trackerHref } from "./tracker-cover";

function tracker(overrides: Partial<SeriesTracker> = {}): SeriesTracker {
  return {
    id: 1,
    source: "asura",
    series_id: "lookism",
    series_title: "Lookism",
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

describe("trackerCoverUrl", () => {
  it("prefers the local cover once the series has been imported", () => {
    expect(trackerCoverUrl(tracker({ local_series_id: 12 }))).toMatch(
      /\/library\/covers\/12$/,
    );
  });

  it("falls back to the source cover when there is no local copy", () => {
    expect(trackerCoverUrl(tracker())).toMatch(
      /\/sources\/asura\/series\/lookism\/cover$/,
    );
  });

  it("encodes a series id containing slashes", () => {
    // Source ids are opaque per-source strings and regularly contain slashes;
    // interpolating one raw would build a path that resolves elsewhere.
    const url = trackerCoverUrl(tracker({ series_id: "webtoon/lookism/123" }));

    expect(url).toMatch(/\/series\/webtoon%2Flookism%2F123\/cover$/);
  });

  it("returns null rather than a URL it knows will 404", () => {
    expect(trackerCoverUrl(tracker({ source: "", series_id: "" }))).toBeNull();
  });
});

describe("trackerHref", () => {
  it("opens the local detail page when the series has been imported", () => {
    expect(trackerHref(tracker({ local_series_id: 12 }))).toBe("/library/12");
  });

  it("opens the source detail page otherwise, with the id encoded", () => {
    expect(trackerHref(tracker({ series_id: "a/b" }))).toBe(
      "/sources/asura/series/a%2Fb",
    );
  });
});
