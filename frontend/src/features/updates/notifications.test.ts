import { describe, expect, it } from "vitest";
import {
  buildNotificationRows,
  describeCheckSchedule,
  notificationSilencedReason,
  summarizeNotificationCoverage,
} from "./notifications";
import type { SeriesTracker, UpdateSettings } from "./types";

function settings(overrides: Partial<UpdateSettings> = {}): UpdateSettings {
  return {
    enabled: true,
    check_interval_minutes: 60,
    notify_enabled: true,
    auto_download_enabled: false,
    check_on_startup: true,
    last_run_at: null,
    updated_at: null,
    ...overrides,
  };
}

function tracker(overrides: Partial<SeriesTracker> = {}): SeriesTracker {
  return {
    id: 1,
    source: "mangadex",
    series_id: "series-1",
    series_title: "Solo Leveling",
    track_kind: "followed",
    local_series_id: null,
    enabled: true,
    notify: true,
    auto_download: false,
    check_interval_minutes: null,
    known_chapter_count: 10,
    last_checked_at: "2026-07-28T10:00:00Z",
    last_error: null,
    created_at: null,
    updated_at: null,
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
      settings({ last_run_at: "2026-07-28T11:30:00Z", check_interval_minutes: 60 }),
      NOON,
    );

    expect(schedule?.estimatedNextRunAt).toBe("2026-07-28T12:30:00.000Z");
    expect(schedule?.overdueByMinutes).toBeNull();
    expect(schedule?.overdue).toBe(false);
  });

  it("does not call a single missed interval overdue (scheduler jitter)", () => {
    // Due at 11:00, now 12:00 -> 60 minutes late with a 60 minute interval.
    const schedule = describeCheckSchedule(
      settings({ last_run_at: "2026-07-28T10:00:00Z", check_interval_minutes: 60 }),
      NOON,
    );

    expect(schedule?.overdueByMinutes).toBe(60);
    expect(schedule?.overdue).toBe(false);
  });

  it("flags overdue once a whole extra interval has elapsed", () => {
    const schedule = describeCheckSchedule(
      settings({ last_run_at: "2026-07-28T08:00:00Z", check_interval_minutes: 60 }),
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
    const schedule = describeCheckSchedule(settings({ last_run_at: "not a date" }), NOON);

    expect(schedule?.neverRun).toBe(true);
    expect(schedule?.estimatedNextRunAt).toBeNull();
  });
});

describe("notificationSilencedReason", () => {
  it("is null when every switch is on", () => {
    expect(notificationSilencedReason(tracker(), settings())).toBeNull();
  });

  it("reports the global check switch before anything else", () => {
    const reason = notificationSilencedReason(
      tracker({ enabled: false, notify: false }),
      settings({ enabled: false, notify_enabled: false }),
    );

    expect(reason).toBe("Automatic update checks are off.");
  });

  it("reports the global notify switch before the per-series ones", () => {
    const reason = notificationSilencedReason(
      tracker({ notify: false }),
      settings({ notify_enabled: false }),
    );

    expect(reason).toBe("New-chapter notifications are off for every series.");
  });

  it("reports a disabled tracker, which is never even checked", () => {
    expect(notificationSilencedReason(tracker({ enabled: false }), settings())).toBe(
      "This series is excluded from update checks.",
    );
  });

  it("reports the per-series notify switch last", () => {
    expect(notificationSilencedReason(tracker({ notify: false }), settings())).toBe(
      "Notifications are off for this series.",
    );
  });
});

describe("buildNotificationRows", () => {
  it("is empty when there are no trackers", () => {
    expect(buildNotificationRows(undefined, settings())).toEqual([]);
    expect(buildNotificationRows([], settings())).toEqual([]);
  });

  it("sorts by title then source", () => {
    const rows = buildNotificationRows(
      [
        tracker({ id: 1, series_title: "Omniscient Reader", source: "mangadex" }),
        tracker({ id: 2, series_title: "Solo Leveling", source: "mangakatana" }),
        tracker({ id: 3, series_title: "Solo Leveling", source: "mangadex" }),
      ],
      settings(),
    );

    expect(rows.map((row) => row.tracker.id)).toEqual([1, 3, 2]);
  });

  it("keeps duplicated follows as separate rows and marks them", () => {
    const rows = buildNotificationRows(
      [
        tracker({ id: 1, series_title: "Solo Leveling", source: "mangadex" }),
        tracker({ id: 2, series_title: "  solo leveling ", source: "mangakatana" }),
        tracker({ id: 3, series_title: "Omniscient Reader", source: "mangadex" }),
      ],
      settings(),
    );

    // Both duplicates survive -- de-duplication is deliberately not applied.
    expect(rows).toHaveLength(3);
    expect(rows.filter((row) => row.duplicateTitle).map((row) => row.tracker.id).sort()).toEqual([
      1, 2,
    ]);
    expect(rows.find((row) => row.tracker.id === 3)?.duplicateTitle).toBe(false);
  });

  it("marks a row silenced when the global notify switch is off", () => {
    const rows = buildNotificationRows([tracker()], settings({ notify_enabled: false }));

    expect(rows[0].effectiveNotify).toBe(false);
    expect(rows[0].silencedReason).toBe(
      "New-chapter notifications are off for every series.",
    );
  });
});

describe("summarizeNotificationCoverage", () => {
  it("counts notifying, silenced, and failing rows", () => {
    const rows = buildNotificationRows(
      [
        tracker({ id: 1 }),
        tracker({ id: 2, notify: false }),
        tracker({ id: 3, last_error: "connector returned 403" }),
        tracker({ id: 4, enabled: false, last_error: "connector returned 403" }),
      ],
      settings(),
    );

    expect(summarizeNotificationCoverage(rows)).toEqual({
      total: 4,
      notifying: 2,
      silenced: 2,
      failing: 2,
    });
  });
});
