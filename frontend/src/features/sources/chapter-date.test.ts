import { describe, expect, it } from "vitest";

import { chapterDateLabel, chapterUploadedAt } from "./chapter-date";

/** 2026-09-09T12:00:00Z */
const NOW = Date.UTC(2026, 8, 9, 12, 0, 0);

describe("chapterDateLabel", () => {
  it("says nothing when the source published no date", () => {
    expect(chapterDateLabel(null, NOW)).toBeNull();
    expect(chapterDateLabel(undefined, NOW)).toBeNull();
    expect(chapterDateLabel("   ", NOW)).toBeNull();
  });

  it("counts recent chapters in days, which is what a reader is checking", () => {
    expect(chapterDateLabel("2026-09-09T09:00:00Z", NOW)).toBe("Today");
    expect(chapterDateLabel("2026-09-08T09:00:00Z", NOW)).toBe("Yesterday");
    expect(chapterDateLabel("2026-09-06T09:00:00Z", NOW)).toBe("3d ago");
  });

  it("switches to a date once the age stops meaning anything", () => {
    // A week out, "43d ago" tells a reader less than the date does.
    const label = chapterDateLabel("2026-07-28T09:00:00Z", NOW);
    expect(label).not.toMatch(/ago/);
    expect(label).toContain("2026");
  });

  it("reads a naive backend timestamp as UTC, not as local time", () => {
    // The asurascans cache stores "2022-09-19T04:15:19Z"; other paths store the
    // same instant with no designator. Both must land on the same day.
    expect(chapterDateLabel("2026-09-08T23:30:00Z", NOW)).toBe(
      chapterDateLabel("2026-09-08T23:30:00", NOW),
    );
  });

  it("handles a bare calendar date, which is most of what sources publish", () => {
    expect(chapterDateLabel("2026-09-08", NOW)).toBe("Yesterday");
  });

  it("passes a scraped string through rather than swallowing it", () => {
    // Some connectors scrape the site's own wording. It is already the
    // sentence a human was shown; blanking it would lose real information.
    expect(chapterDateLabel("2 days ago", NOW)).toBe("2 days ago");
    expect(chapterDateLabel("Yesterday", NOW)).toBe("Yesterday");
  });

  it("does not promise a future a reader cannot act on", () => {
    // A source clock ahead of ours, or a scheduled chapter.
    expect(chapterDateLabel("2026-09-10T09:00:00Z", NOW)).toBe("Just now");
  });
});

describe("chapterUploadedAt", () => {
  it("reads the live listing's field", () => {
    expect(chapterUploadedAt({ release_date: "2026-09-01" })).toBe("2026-09-01");
  });

  it("reads the cached list's field, which normalises to another name", () => {
    expect(chapterUploadedAt({ published_at: "2026-09-01" })).toBe("2026-09-01");
  });

  it("prefers the live field when a row somehow carries both", () => {
    expect(
      chapterUploadedAt({ release_date: "2026-09-02", published_at: "2026-09-01" }),
    ).toBe("2026-09-02");
  });

  it("is null when a chapter carries neither", () => {
    expect(chapterUploadedAt({})).toBeNull();
    expect(chapterUploadedAt({ release_date: null, published_at: null })).toBeNull();
  });
});
