import { describe, expect, it } from "vitest";
import { computeNewChaptersBanner } from "./hooks";
import type { UpdateNotification } from "./types";

/**
 * The new-chapters banner's visibility is a pure function of the unread
 * notifications and the session dismissal watermark. These exercise that
 * selector directly (no renderer), matching the hook-logic test style used
 * across this suite (see hooks.test.ts).
 */
function notification(overrides: Partial<UpdateNotification> = {}): UpdateNotification {
  return {
    id: 1,
    tracker_id: 1,
    source: "mangadex",
    series_id: "series-1",
    series_title: "Test Series",
    chapter_id: "ch-1",
    chapter_title: "Chapter 1",
    chapter_number: 1,
    is_read: false,
    created_at: null,
    ...overrides,
  };
}

describe("computeNewChaptersBanner", () => {
  it("is hidden when there are no notifications", () => {
    expect(computeNewChaptersBanner(undefined, null)).toEqual({
      show: false,
      count: 0,
      seriesCount: 0,
      latestId: null,
    });
    expect(computeNewChaptersBanner([], null).show).toBe(false);
  });

  it("shows with counts and latest id when unread and never dismissed", () => {
    const state = computeNewChaptersBanner(
      [
        notification({ id: 3, series_id: "a" }),
        notification({ id: 7, series_id: "b" }),
        notification({ id: 5, series_id: "a" }),
      ],
      null,
    );
    expect(state).toEqual({ show: true, count: 3, seriesCount: 2, latestId: 7 });
  });

  it("counts distinct series, not notifications", () => {
    const state = computeNewChaptersBanner(
      [
        notification({ id: 1, series_id: "a" }),
        notification({ id: 2, series_id: "a" }),
        notification({ id: 3, series_id: "a" }),
      ],
      null,
    );
    expect(state.count).toBe(3);
    expect(state.seriesCount).toBe(1);
  });

  it("is hidden after dismissing at the current latest id", () => {
    const items = [notification({ id: 4 }), notification({ id: 9 })];
    const { latestId } = computeNewChaptersBanner(items, null);
    expect(latestId).toBe(9);
    expect(computeNewChaptersBanner(items, 9).show).toBe(false);
  });

  it("re-appears when a newer chapter arrives after dismissal", () => {
    // Dismissed watermark is 9; a notification with id 12 is genuinely newer.
    const state = computeNewChaptersBanner(
      [notification({ id: 9 }), notification({ id: 12 })],
      9,
    );
    expect(state.show).toBe(true);
    expect(state.latestId).toBe(12);
  });

  it("stays hidden when all unread ids are at or below the watermark", () => {
    const state = computeNewChaptersBanner(
      [notification({ id: 2 }), notification({ id: 8 })],
      8,
    );
    expect(state.show).toBe(false);
  });
});
