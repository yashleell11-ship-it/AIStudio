import { describe, expect, it } from "vitest";
import {
  formatUtcDate,
  formatUtcDateTime,
  parseUtcTimestamp,
  utcMinutesFromNow,
} from "./utc-time";

describe("parseUtcTimestamp", () => {
  it("reads a naive backend timestamp as UTC, not local time", () => {
    expect(parseUtcTimestamp("2026-09-04T03:00:00")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0),
    );
  });

  it("keeps sub-second precision", () => {
    expect(parseUtcTimestamp("2026-09-04T03:00:00.250")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0, 250),
    );
  });

  it("leaves a timestamp that already says Z alone", () => {
    expect(parseUtcTimestamp("2026-09-04T03:00:00Z")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0),
    );
  });

  it("respects an explicit offset instead of overriding it", () => {
    expect(parseUtcTimestamp("2026-09-04T08:30:00+05:30")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0),
    );
    expect(parseUtcTimestamp("2026-09-03T19:00:00-0800")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0),
    );
  });

  it("accepts the space-separated SQLite form", () => {
    expect(parseUtcTimestamp("2026-09-04 03:00:00")).toBe(
      Date.UTC(2026, 8, 4, 3, 0, 0),
    );
  });

  it("leaves a date-only value to the spec, which already reads it as UTC", () => {
    expect(parseUtcTimestamp("2026-09-04")).toBe(Date.UTC(2026, 8, 4));
  });

  it("returns null for missing or unparseable values", () => {
    expect(parseUtcTimestamp(null)).toBeNull();
    expect(parseUtcTimestamp(undefined)).toBeNull();
    expect(parseUtcTimestamp("")).toBeNull();
    expect(parseUtcTimestamp("not a date")).toBeNull();
  });
});

// The bug these guard against only shows up away from UTC: a naive backend
// timestamp read as local time lands 5.5h early here. Pinned so the tests fail
// on a UTC CI box too.
process.env.TZ = "Asia/Kolkata";

describe("formatUtcDateTime", () => {
  it("renders a naive backend timestamp at its real instant", () => {
    expect(formatUtcDateTime("2026-09-04T18:30:00")).toBe(
      new Date(Date.UTC(2026, 8, 4, 18, 30, 0)).toLocaleString(),
    );
  });

  it("agrees with the same timestamp written with a Z", () => {
    expect(formatUtcDateTime("2026-09-04T18:30:00")).toBe(
      formatUtcDateTime("2026-09-04T18:30:00Z"),
    );
  });

  it("says so instead of rendering an absent or broken value", () => {
    expect(formatUtcDateTime(null)).toBe("Never");
    expect(formatUtcDateTime("nonsense")).toBe("Unknown");
    expect(formatUtcDateTime(null, { missing: "—" })).toBe("—");
  });
});

describe("formatUtcDate", () => {
  it("does not date an evening read to the day before", () => {
    // 2026-09-04 20:00 UTC is already 2026-09-05 in IST.
    expect(formatUtcDate("2026-09-04T20:00:00")).toBe(
      new Date(Date.UTC(2026, 8, 4, 20, 0, 0)).toLocaleDateString(),
    );
  });

  it("renders nothing for an absent or broken value by default", () => {
    expect(formatUtcDate(null)).toBe("");
    expect(formatUtcDate("nonsense")).toBe("");
  });
});

describe("utcMinutesFromNow", () => {
  it("measures a naive backend timestamp from the right instant", () => {
    const now = Date.UTC(2026, 8, 4, 18, 35, 0);
    expect(utcMinutesFromNow("2026-09-04T18:30:00", now)).toBe(5);
  });

  it("reports a future estimate as negative", () => {
    const now = Date.UTC(2026, 8, 4, 18, 30, 0);
    expect(utcMinutesFromNow("2026-09-04T19:00:00Z", now)).toBe(-30);
  });

  it("returns null when there is nothing to measure", () => {
    expect(utcMinutesFromNow(null, Date.now())).toBeNull();
    expect(utcMinutesFromNow("nonsense", Date.now())).toBeNull();
  });
});
