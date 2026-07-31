import { describe, expect, it } from "vitest";
import type { SeriesTracker, UpdateNotification } from "@/features/updates/types";
import { followedSeriesMeta, followedSubtitle } from "./followed-meta";

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

function notification(overrides: Partial<UpdateNotification> = {}): UpdateNotification {
  return {
    id: 1,
    tracker_id: 1,
    source: "asura",
    series_id: "lookism",
    series_title: "Lookism",
    chapter_id: "c1",
    chapter_title: "Chapter 1",
    chapter_number: 1,
    is_read: false,
    created_at: null,
    ...overrides,
  };
}

describe("followedSeriesMeta", () => {
  it("counts only unread notifications belonging to the tracker", () => {
    const meta = followedSeriesMeta(tracker({ id: 7 }), [
      notification({ id: 1, tracker_id: 7, is_read: false }),
      notification({ id: 2, tracker_id: 7, is_read: true }),
      // A different series' unread notification must not inflate this card.
      notification({ id: 3, tracker_id: 8, is_read: false }),
    ]);

    expect(meta.unreadCount).toBe(1);
  });

  it("picks the highest chapter number as the latest", () => {
    const meta = followedSeriesMeta(tracker(), [
      notification({ id: 1, chapter_number: 118 }),
      notification({ id: 2, chapter_number: 120 }),
      notification({ id: 3, chapter_number: 119 }),
    ]);

    expect(meta.latestChapterLabel).toBe("Chapter 120");
  });

  it("falls back to the newest timestamp when chapter numbers are absent", () => {
    const meta = followedSeriesMeta(tracker(), [
      notification({
        id: 1,
        chapter_number: null,
        chapter_title: "Prologue",
        created_at: "2026-01-01T00:00:00Z",
      }),
      notification({
        id: 2,
        chapter_number: null,
        chapter_title: "Epilogue",
        created_at: "2026-06-01T00:00:00Z",
      }),
    ]);

    expect(meta.latestChapterLabel).toBe("Epilogue");
  });

  it("reports nothing when the series has never produced a notification", () => {
    expect(followedSeriesMeta(tracker(), [])).toEqual({
      unreadCount: 0,
      latestChapterLabel: null,
    });
  });
});

describe("followedSubtitle", () => {
  it("prefers the latest chapter we were actually notified about", () => {
    const subtitle = followedSubtitle(tracker({ known_chapter_count: 5 }), {
      unreadCount: 0,
      latestChapterLabel: "Chapter 120",
    });

    expect(subtitle).toBe("Latest: Chapter 120");
  });

  it("never claims a chapter count the update checker has not populated", () => {
    // known_chapter_count is 0 for every freshly-followed series, so "0
    // chapters" would be a lie on the most common card on the screen.
    const subtitle = followedSubtitle(tracker({ known_chapter_count: 0 }), {
      unreadCount: 0,
      latestChapterLabel: null,
    });

    expect(subtitle).toBeNull();
  });

  it("falls back to a real chapter count when one exists", () => {
    expect(
      followedSubtitle(tracker({ known_chapter_count: 1 }), {
        unreadCount: 0,
        latestChapterLabel: null,
      }),
    ).toBe("1 chapter");

    expect(
      followedSubtitle(tracker({ known_chapter_count: 42 }), {
        unreadCount: 0,
        latestChapterLabel: null,
      }),
    ).toBe("42 chapters");
  });
});
