import type { SeriesTracker, UpdateSettings } from "./types";

/**
 * Pure logic behind the consolidated notification settings section.
 *
 * New-chapter notifications are an AND of three switches, all of them
 * server-side (backend/services/update_service.py:1308 and
 * update_service.py:1253):
 *
 *   1. `settings.enabled`      — the checker runs at all
 *   2. `tracker.enabled`       — this series is included in a check
 *      (`_select_trackers_for_check` filters `enabled IS TRUE`)
 *   3. `settings.notify_enabled AND tracker.notify` — a notification row is written
 *
 * The UI has to model all three, because turning off any one of them silences a
 * series and only one of them is obvious from the row itself.
 */

/** Minutes the scheduler is allowed to overshoot before a run reads as late. */
const OVERDUE_INTERVAL_FACTOR = 2;

export interface CheckSchedule {
  enabled: boolean;
  intervalMinutes: number;
  lastRunAt: string | null;
  /**
   * When the next check is expected, as an ISO string.
   *
   * An ESTIMATE, deliberately: the scheduler thread sleeps on its own loop from
   * process start (backend/services/update_scheduler.py:129-135) and the API
   * exposes no next-run timestamp, so the only thing derivable client-side is
   * "last finished run + interval". Null until a run has finished.
   */
  estimatedNextRunAt: string | null;
  /** Minutes past the estimate, or null when it is not past yet. */
  overdueByMinutes: number | null;
  /** Past the estimate by a whole extra interval — a run was probably missed. */
  overdue: boolean;
  /** No check has ever finished, so there is nothing to schedule from. */
  neverRun: boolean;
}

export function describeCheckSchedule(
  settings: UpdateSettings | undefined,
  nowMs: number,
): CheckSchedule | null {
  if (!settings) {
    return null;
  }
  const intervalMinutes = settings.check_interval_minutes;
  const lastRunAt = settings.last_run_at;
  if (!lastRunAt) {
    return {
      enabled: settings.enabled,
      intervalMinutes,
      lastRunAt: null,
      estimatedNextRunAt: null,
      overdueByMinutes: null,
      overdue: false,
      neverRun: true,
    };
  }

  const lastRunMs = Date.parse(lastRunAt);
  if (Number.isNaN(lastRunMs)) {
    // An unparseable timestamp is a data problem, not a schedule: report it as
    // "never run" rather than inventing a next-run time from NaN.
    return {
      enabled: settings.enabled,
      intervalMinutes,
      lastRunAt,
      estimatedNextRunAt: null,
      overdueByMinutes: null,
      overdue: false,
      neverRun: true,
    };
  }

  const intervalMs = intervalMinutes * 60_000;
  const nextRunMs = lastRunMs + intervalMs;
  const lateByMs = nowMs - nextRunMs;

  return {
    enabled: settings.enabled,
    intervalMinutes,
    lastRunAt,
    estimatedNextRunAt: new Date(nextRunMs).toISOString(),
    overdueByMinutes: lateByMs > 0 ? Math.floor(lateByMs / 60_000) : null,
    // One interval late is normal jitter (the scheduler sleeps from its own
    // start, not from the last run). Two is a missed cycle.
    overdue: settings.enabled && lateByMs > intervalMs * (OVERDUE_INTERVAL_FACTOR - 1),
    neverRun: false,
  };
}

export interface NotificationTrackerRow {
  tracker: SeriesTracker;
  /**
   * Whether this series will actually produce a notification, accounting for
   * the global switches as well as the row's own.
   */
  effectiveNotify: boolean;
  /** Why it will not, when it will not. Null when it will. */
  silencedReason: string | null;
  /**
   * Another followed row in this list carries the same title. Surfaced, never
   * merged: two follows of one story on two sources are two independent
   * trackers server-side and each notifies on its own — that is intended, so
   * the UI labels it instead of hiding one of them.
   */
  duplicateTitle: boolean;
}

function normalizeTitle(title: string): string {
  return title.trim().toLowerCase();
}

/**
 * Builds the per-series notification list.
 *
 * No de-duplication: duplicated follows are allowed to notify separately, so
 * every tracker keeps its own row and its own switch. `duplicateTitle` just
 * marks the ones that share a title so the owner can tell why a chapter
 * announced itself twice.
 */
export function buildNotificationRows(
  trackers: SeriesTracker[] | undefined,
  settings: UpdateSettings | undefined,
): NotificationTrackerRow[] {
  const rows = trackers ?? [];
  const titleCounts = new Map<string, number>();
  for (const tracker of rows) {
    const key = normalizeTitle(tracker.series_title);
    titleCounts.set(key, (titleCounts.get(key) ?? 0) + 1);
  }

  return rows
    .map((tracker) => {
      const silencedReason = notificationSilencedReason(tracker, settings);
      return {
        tracker,
        effectiveNotify: silencedReason === null,
        silencedReason,
        duplicateTitle: (titleCounts.get(normalizeTitle(tracker.series_title)) ?? 0) > 1,
      };
    })
    .sort(
      (a, b) =>
        a.tracker.series_title.localeCompare(b.tracker.series_title) ||
        a.tracker.source.localeCompare(b.tracker.source),
    );
}

/**
 * The first switch that stops this series from notifying, in the order the
 * server evaluates them, or null when nothing does. Reported one reason at a
 * time on purpose: fixing the outermost switch is what the owner has to do
 * first anyway, and listing all three at once reads as three separate faults.
 */
export function notificationSilencedReason(
  tracker: SeriesTracker,
  settings: UpdateSettings | undefined,
): string | null {
  if (settings && !settings.enabled) {
    return "Automatic update checks are off.";
  }
  if (settings && !settings.notify_enabled) {
    return "New-chapter notifications are off for every series.";
  }
  if (!tracker.enabled) {
    return "This series is excluded from update checks.";
  }
  if (!tracker.notify) {
    return "Notifications are off for this series.";
  }
  return null;
}

export interface NotificationCoverage {
  total: number;
  /** Rows that will actually notify once a new chapter appears. */
  notifying: number;
  /** Rows silenced by their own switch or by a global one. */
  silenced: number;
  /** Rows whose last check recorded an error — they may be notifying nothing. */
  failing: number;
}

export function summarizeNotificationCoverage(
  rows: NotificationTrackerRow[],
): NotificationCoverage {
  const notifying = rows.filter((row) => row.effectiveNotify).length;
  return {
    total: rows.length,
    notifying,
    silenced: rows.length - notifying,
    failing: rows.filter((row) => row.tracker.last_error !== null).length,
  };
}
