import { describe, expect, it } from "vitest";
import { parseUtcTimestamp } from "./utc-time";

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
