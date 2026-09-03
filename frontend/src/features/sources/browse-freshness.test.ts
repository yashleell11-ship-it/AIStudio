import { describe, expect, it } from "vitest";
import { describeBrowseFreshness, formatRelativeAge } from "./browse-freshness";

const NOW = Date.UTC(2026, 8, 4, 12, 0, 0);
/** The backend serialises UTC with no `Z` — the format this must survive. */
function naive(offsetMs: number): string {
  return new Date(NOW - offsetMs).toISOString().replace("Z", "");
}

describe("formatRelativeAge", () => {
  it("calls anything under three quarters of a minute 'just now'", () => {
    expect(formatRelativeAge(0)).toBe("just now");
    expect(formatRelativeAge(44_000)).toBe("just now");
  });

  it("reads a clock skew into the future as 'just now'", () => {
    expect(formatRelativeAge(-60_000)).toBe("just now");
  });

  it("counts in minutes up to an hour and a half", () => {
    expect(formatRelativeAge(3 * 60_000)).toBe("3 min ago");
    expect(formatRelativeAge(89 * 60_000)).toBe("89 min ago");
  });

  it("switches to hours, then days", () => {
    expect(formatRelativeAge(2 * 3_600_000)).toBe("2 h ago");
    expect(formatRelativeAge(35 * 3_600_000)).toBe("35 h ago");
    expect(formatRelativeAge(3 * 86_400_000)).toBe("3 d ago");
  });

  it("never says '0 min ago'", () => {
    expect(formatRelativeAge(46_000)).toBe("1 min ago");
  });
});

describe("describeBrowseFreshness", () => {
  it("reads the naive UTC timestamp as UTC", () => {
    const freshness = describeBrowseFreshness(
      { status: "fresh", stale: false, fetched_at: naive(3 * 60_000) },
      NOW,
    );

    expect(freshness?.tone).toBe("fresh");
    expect(freshness?.label).toBe("Updated 3 min ago");
  });

  it("says so when the source could not be reached", () => {
    const freshness = describeBrowseFreshness(
      { status: "stale", stale: true, fetched_at: naive(5 * 3_600_000) },
      NOW,
    );

    expect(freshness?.tone).toBe("stale");
    expect(freshness?.label).toBe("Saved copy · 5 h ago");
    expect(freshness?.detail).toContain("could not be reached");
  });

  it("trusts the stale flag even when the status string disagrees", () => {
    const freshness = describeBrowseFreshness(
      { status: "fresh", stale: true, fetched_at: naive(60_000) },
      NOW,
    );

    expect(freshness?.tone).toBe("stale");
  });

  it("distinguishes a live fetch from a cache hit in the detail text", () => {
    const live = describeBrowseFreshness(
      { status: "live", stale: false, fetched_at: naive(0) },
      NOW,
    );
    const cached = describeBrowseFreshness(
      { status: "fresh", stale: false, fetched_at: naive(10 * 60_000) },
      NOW,
    );

    expect(live?.detail).toContain("Fetched from the source");
    expect(cached?.detail).toContain("saved catalog");
  });

  it("says nothing when there is no cache block or no usable timestamp", () => {
    expect(describeBrowseFreshness(null, NOW)).toBeNull();
    expect(describeBrowseFreshness(undefined, NOW)).toBeNull();
    expect(
      describeBrowseFreshness({ status: "fresh", stale: false, fetched_at: "" }, NOW),
    ).toBeNull();
    expect(
      describeBrowseFreshness(
        { status: "fresh", stale: false, fetched_at: "nonsense" },
        NOW,
      ),
    ).toBeNull();
  });
});
