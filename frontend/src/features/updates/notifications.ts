import type { UpdateSettings } from "./types";

/**
 * Pure logic behind the update-check schedule strip.
 *
 * New-chapter notifications are gated server-side by an AND of:
 *   1. `settings.enabled`        — the checker runs at all
 *   2. `settings.notify_enabled` — a notification row is written
 *   3. the followed series' own `notify` flag (patched via `/library/series/{id}`)
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
   * process start and the API exposes no next-run timestamp, so the only thing
   * derivable client-side is "last finished run + interval". Null until a run
   * has finished.
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
    overdue:
      settings.enabled &&
      lateByMs > intervalMs * (OVERDUE_INTERVAL_FACTOR - 1),
    neverRun: false,
  };
}
