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

  it("counts by calendar day, not by elapsed hours", () => {
    // Posted at 23:00 last night: two hours old, but it is Yesterday's chapter
    // and a reader scanning the list reads it that way. This used to return
    // "Today" here while the Flutter client returned "Yesterday" for the same
    // chapter. Built from LOCAL constructors so the assertion holds in any
    // timezone the suite runs in — the rule is about the reader's calendar.
    const lastNight = new Date(2026, 8, 8, 23);
    const earlyToday = new Date(2026, 8, 9, 1).getTime();

    expect(chapterDateLabel(lastNight.toISOString(), earlyToday)).toBe("Yesterday");
  });

  it("reads a bare calendar day as a DAY, not as UTC midnight", () => {
    // A date-only string names a day, not an instant. Read as UTC midnight it
    // lands on the previous day anywhere west of Greenwich, which is the
    // off-by-one parseCalendarDay exists to prevent.
    const noonToday = new Date(2026, 8, 9, 12).getTime();

    expect(chapterDateLabel("2026-09-09", noonToday)).toBe("Today");
    expect(chapterDateLabel("2026-09-08", noonToday)).toBe("Yesterday");
  });

  it("passes through the non-ISO shapes real connectors publish", () => {
    // Each of these is asserted in the backend's own connector tests. The
    // Flutter client used to parse them with a bare DateTime.tryParse, get
    // null, and render no date at all while the web showed the source's wording.
    expect(chapterDateLabel("18 Mar 2021", NOW)).toBe("18 Mar 2021");
    expect(chapterDateLabel("Apr 22,2016", NOW)).toBe("Apr 22,2016");
    expect(chapterDateLabel("Nov 05,2018", NOW)).toBe("Nov 05,2018");
    expect(chapterDateLabel("2019/07/13", NOW)).toBe("2019/07/13");
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
