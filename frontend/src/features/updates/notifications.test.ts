import { describe, expect, it } from "vitest";
import { describeCheckSchedule } from "./notifications";
import type { UpdateSettings } from "./types";

function settings(overrides: Partial<UpdateSettings> = {}): UpdateSettings {
  return {
    enabled: true,
    check_interval_minutes: 60,
    notify_enabled: true,
    check_on_startup: true,
    last_run_at: null,
    ...overrides,
  };
}

const NOON = Date.parse("2026-07-28T12:00:00Z");

describe("describeCheckSchedule", () => {
  it("returns null while settings are still loading", () => {
    expect(describeCheckSchedule(undefined, NOON)).toBeNull();
  });

  it("reports never-run when no check has finished", () => {
    const schedule = describeCheckSchedule(settings({ last_run_at: null }), NOON);

    expect(schedule?.neverRun).toBe(true);
    expect(schedule?.estimatedNextRunAt).toBeNull();
    expect(schedule?.overdue).toBe(false);
  });

  it("estimates the next run as last run plus the interval", () => {
    const schedule = describeCheckSchedule(
      settings({
        last_run_at: "2026-07-28T11:30:00Z",
        check_interval_minutes: 60,
      }),
      NOON,
    );

    expect(schedule?.estimatedNextRunAt).toBe("2026-07-28T12:30:00.000Z");
    expect(schedule?.overdueByMinutes).toBeNull();
    expect(schedule?.overdue).toBe(false);
  });

  it("does not call a single missed interval overdue (scheduler jitter)", () => {
    const schedule = describeCheckSchedule(
      settings({
        last_run_at: "2026-07-28T10:00:00Z",
        check_interval_minutes: 60,
      }),
      NOON,
    );

    expect(schedule?.overdueByMinutes).toBe(60);
    expect(schedule?.overdue).toBe(false);
  });

  it("flags overdue once a whole extra interval has elapsed", () => {
    const schedule = describeCheckSchedule(
      settings({
        last_run_at: "2026-07-28T08:00:00Z",
        check_interval_minutes: 60,
      }),
      NOON,
    );

    expect(schedule?.overdueByMinutes).toBe(180);
    expect(schedule?.overdue).toBe(true);
  });

  it("never reports overdue while automatic checks are disabled", () => {
    const schedule = describeCheckSchedule(
      settings({ enabled: false, last_run_at: "2026-01-01T00:00:00Z" }),
      NOON,
    );

    expect(schedule?.overdue).toBe(false);
    expect(schedule?.enabled).toBe(false);
  });

  it("treats an unparseable last_run_at as never-run rather than inventing a time", () => {
    const schedule = describeCheckSchedule(
      settings({ last_run_at: "not a date" }),
      NOON,
    );

    expect(schedule?.neverRun).toBe(true);
    expect(schedule?.estimatedNextRunAt).toBeNull();
  });
});
