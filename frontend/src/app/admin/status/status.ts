import type { CheckSchedule } from "@/features/updates/notifications";
import type {
  SeriesTracker,
  UpdateRun,
  UpdateSettings,
  UpdateSource,
} from "@/features/updates/types";
import type { SystemStatus } from "@/services/system";
import { ApiError } from "@/types/api";

/**
 * Pure status derivation for the admin status page.
 *
 * Everything here is computed from responses that already exist:
 *   GET /health                  -> reachability, name, version
 *   GET /updates/settings, /runs -> checker schedule and run history
 *   GET /updates/trackers        -> per-source health (see deriveSourceHealth)
 *
 * Nothing is invented. Where the backend exposes no number, the corresponding
 * field is `unknown` and the UI says so rather than showing a plausible zero.
 */

export type HealthState = "ok" | "warn" | "down" | "unknown";

const STATE_SEVERITY: Record<HealthState, number> = {
  ok: 0,
  unknown: 1,
  warn: 2,
  down: 3,
};

/** The most severe of the given states; `ok` for an empty list. */
export function worstState(states: HealthState[]): HealthState {
  return states.reduce<HealthState>(
    (worst, state) => (STATE_SEVERITY[state] > STATE_SEVERITY[worst] ? state : worst),
    "ok",
  );
}

// --- backend -----------------------------------------------------------------

export interface BackendHealth {
  state: HealthState;
  reachable: boolean;
  name: string | null;
  version: string | null;
  message: string;
}

/**
 * Reachability of the API itself, from the public `/health` probe
 * (backend/routes/system.py:43). A transport failure surfaces as ApiError with
 * status 0, which is the case worth distinguishing: "the server is not there"
 * reads very differently from "the server answered with an error".
 */
export function deriveBackendHealth(input: {
  status: SystemStatus | undefined;
  error: unknown;
  isLoading: boolean;
}): BackendHealth {
  if (input.error) {
    const isNetwork = input.error instanceof ApiError && input.error.status === 0;
    return {
      state: "down",
      reachable: false,
      name: null,
      version: null,
      message: isNetwork
        ? "The backend did not answer. It may be stopped, restarting, or unreachable from this browser."
        : input.error instanceof ApiError
          ? `The health probe failed: ${input.error.message}`
          : "The health probe failed.",
    };
  }
  if (input.isLoading || !input.status) {
    return {
      state: "unknown",
      reachable: false,
      name: null,
      version: null,
      message: "Contacting the backend…",
    };
  }
  return {
    state: input.status.status === "online" ? "ok" : "warn",
    reachable: true,
    name: input.status.name,
    version: input.status.version,
    message:
      input.status.status === "online"
        ? "The API is answering health probes."
        : `The API reported status "${input.status.status}".`,
  };
}

// --- update checker ----------------------------------------------------------

export interface CheckerHealth {
  state: HealthState;
  schedule: CheckSchedule | null;
  /** The most recent run, whatever its outcome. */
  lastRun: UpdateRun | null;
  /** A run currently in progress, if the history shows one. */
  runningRun: UpdateRun | null;
  /** Runs that ended in `failed`, newest first. */
  failedRuns: UpdateRun[];
  /** Failed runs at the head of the history — the current failing streak. */
  consecutiveFailures: number;
  message: string;
}

/**
 * Health of the update checker.
 *
 * Important caveat encoded here: a run whose status is `completed` does NOT
 * mean every series was checked successfully. `_check_tracker` swallows a
 * connector error, records it on the tracker as `last_error`, and lets the run
 * finish (backend/services/update_service.py:1279-1290). That is exactly how a
 * dead connector goes unnoticed — so the run history alone is never enough, and
 * `deriveSourceHealth` below is the part that actually catches it.
 */
export function deriveCheckerHealth(input: {
  settings: UpdateSettings | undefined;
  runs: UpdateRun[] | undefined;
  schedule: CheckSchedule | null;
  isLoading: boolean;
}): CheckerHealth {
  const runs = input.runs ?? [];
  const lastRun = runs[0] ?? null;
  const runningRun = runs.find((run) => run.status === "running") ?? null;
  const failedRuns = runs.filter((run) => run.status === "failed");

  let consecutiveFailures = 0;
  for (const run of runs) {
    if (run.status === "running") continue;
    if (run.status !== "failed") break;
    consecutiveFailures += 1;
  }

  const base = {
    schedule: input.schedule,
    lastRun,
    runningRun,
    failedRuns,
    consecutiveFailures,
  };

  if (input.isLoading || !input.settings) {
    return { ...base, state: "unknown", message: "Loading the update checker's history…" };
  }
  if (!input.settings.enabled) {
    return {
      ...base,
      state: "warn",
      message: "Automatic update checks are switched off, so no series is being checked.",
    };
  }
  if (consecutiveFailures > 0) {
    return {
      ...base,
      state: "down",
      message:
        consecutiveFailures === 1
          ? "The last update check failed."
          : `The last ${consecutiveFailures} update checks failed.`,
    };
  }
  if (input.schedule?.neverRun) {
    return {
      ...base,
      state: "warn",
      message: "No update check has finished yet, so there is nothing to schedule from.",
    };
  }
  if (input.schedule?.overdue) {
    return {
      ...base,
      state: "warn",
      message: `The next check was expected ${input.schedule.overdueByMinutes} minutes ago. The scheduler may not be running.`,
    };
  }
  return {
    ...base,
    state: "ok",
    message: "The update checker is running on schedule.",
  };
}

// --- per-source health -------------------------------------------------------

export interface SourceHealth {
  source: string;
  /** Display name from GET /updates/sources, when that source is installed. */
  name: string | null;
  /** Followed + downloaded series pointing at this source. */
  trackedCount: number;
  /** Trackers whose last check recorded an error. */
  failingCount: number;
  /** The most recent error recorded against this source, if any. */
  lastError: string | null;
  /** Most recent successful-or-attempted check across this source's trackers. */
  lastCheckedAt: string | null;
  state: HealthState;
  message: string;
}

function laterIso(a: string | null, b: string | null): string | null {
  if (!a) return b;
  if (!b) return a;
  return a >= b ? a : b;
}

/**
 * Per-source health, derived from tracker rows.
 *
 * There is no source-health endpoint: `GET /sources` lists installed connectors
 * and says nothing about whether they still work. What the backend does record
 * is `SeriesTracker.last_error`, written whenever a connector throws during a
 * check and cleared on the next success (update_service.py:1282, 1301, 1336).
 * Grouping trackers by source therefore gives a genuine, if indirect, "is this
 * connector still alive" signal — and it is the only one available.
 *
 * Consequences, which the page states plainly rather than papering over:
 *   - a source with no followed/downloaded series has no signal at all
 *     (`unknown`, not `ok`);
 *   - trackers are scoped per (user, profile), so this reflects the profile the
 *     page is being viewed under.
 */
export function deriveSourceHealth(
  trackers: SeriesTracker[] | undefined,
  sources: UpdateSource[] | undefined,
): SourceHealth[] {
  const names = new Map((sources ?? []).map((source) => [source.source_type, source.name]));
  const bySource = new Map<string, SourceHealth>();
  /** When each source's currently-reported error was recorded, for freshness. */
  const errorRecordedAt = new Map<string, string | null>();

  const ensure = (source: string): SourceHealth => {
    const existing = bySource.get(source);
    if (existing) return existing;
    const created: SourceHealth = {
      source,
      name: names.get(source) ?? null,
      trackedCount: 0,
      failingCount: 0,
      lastError: null,
      lastCheckedAt: null,
      state: "unknown",
      message: "",
    };
    bySource.set(source, created);
    return created;
  };

  // Seed every installed source so one that has quietly lost all its follows
  // still appears, rather than vanishing from the report.
  for (const source of sources ?? []) {
    ensure(source.source_type);
  }

  for (const tracker of trackers ?? []) {
    const row = ensure(tracker.source);
    row.trackedCount += 1;
    row.lastCheckedAt = laterIso(row.lastCheckedAt, tracker.last_checked_at);
    if (tracker.last_error) {
      row.failingCount += 1;
      // Keep the error belonging to the most recently checked failing tracker:
      // that is the freshest evidence of what is wrong.
      const currentAt = errorRecordedAt.get(tracker.source) ?? null;
      if (row.lastError === null || laterIso(currentAt, tracker.last_checked_at) !== currentAt) {
        row.lastError = tracker.last_error;
        errorRecordedAt.set(tracker.source, tracker.last_checked_at);
      }
    }
  }

  const rows = Array.from(bySource.values()).map((row) => {
    if (row.trackedCount === 0) {
      return {
        ...row,
        state: "unknown" as HealthState,
        message: "No followed or downloaded series uses this source, so there is nothing to report.",
      };
    }
    if (row.failingCount === row.trackedCount) {
      return {
        ...row,
        state: "down" as HealthState,
        message: `Every tracked series on this source failed its last check (${row.failingCount}).`,
      };
    }
    if (row.failingCount > 0) {
      return {
        ...row,
        state: "warn" as HealthState,
        message: `${row.failingCount} of ${row.trackedCount} tracked series failed their last check.`,
      };
    }
    if (row.lastCheckedAt === null) {
      return {
        ...row,
        state: "unknown" as HealthState,
        message: "Tracked, but never checked yet.",
      };
    }
    return {
      ...row,
      state: "ok" as HealthState,
      message: `All ${row.trackedCount} tracked series checked without error.`,
    };
  });

  return rows.sort(
    (a, b) =>
      STATE_SEVERITY[b.state] - STATE_SEVERITY[a.state] ||
      b.failingCount - a.failingCount ||
      a.source.localeCompare(b.source),
  );
}

// --- overall -----------------------------------------------------------------

export interface SystemStatusSummary {
  state: HealthState;
  headline: string;
  /** Everything currently wrong, most severe first. */
  problems: string[];
}

export function deriveSystemSummary(input: {
  backend: BackendHealth;
  checker: CheckerHealth;
  sources: SourceHealth[];
}): SystemStatusSummary {
  const sourceState = worstState(input.sources.map((source) => source.state));
  const state = worstState([
    input.backend.state,
    input.checker.state,
    sourceState,
  ]);

  const problems: string[] = [];
  const push = (health: { state: HealthState; message: string }) => {
    if (health.state === "warn" || health.state === "down") problems.push(health.message);
  };
  push(input.backend);
  push(input.checker);
  for (const source of input.sources) {
    if (source.state === "down" || source.state === "warn") {
      problems.push(`${source.name ?? source.source}: ${source.message}`);
    }
  }

  const headline =
    state === "down"
      ? "Something is broken."
      : state === "warn"
        ? "Running, with warnings."
        : state === "unknown"
          ? "Still gathering status…"
          : "Everything is healthy.";

  return { state, headline, problems };
}
