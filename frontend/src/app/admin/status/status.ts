import type { CheckSchedule } from "@/features/updates/notifications";
import type { UpdateRun, UpdateSettings } from "@/features/updates/types";
import type { SystemStatus } from "@/services/system";
import { ApiError } from "@/types/api";
import type { SourceHealthRow } from "./api";

/**
 * Pure status derivation for the admin status page.
 *
 * Everything here is computed from responses that already exist:
 *   GET /health                  -> reachability, name, version
 *   GET /updates/settings, /runs -> checker schedule and run history
 *   GET /sources/health          -> per-source reachability (see deriveSourceHealth)
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
  /** Display name from GET /sources/health. */
  name: string | null;
  /** Consecutive failed probes recorded against this source. */
  consecutiveFailures: number;
  /** Whether search ordering currently pushes this source down. */
  demoted: boolean;
  /** The most recent error text the source raised, if any. */
  lastError: string | null;
  /** When the source was last probed (accurate to within ~6h — see 1a). */
  lastCheckedAt: string | null;
  /** When the source last answered successfully. */
  lastOkAt: string | null;
  state: HealthState;
  message: string;
}

/**
 * Per-source health, straight from `GET /sources/health` (1a).
 *
 * Health is recorded globally by the federated-search fan-out: every installed
 * source is probed on every search, and a row is written when the outcome
 * changes something observable. The endpoint returns the same rows as
 * `GET /sources`, ordered worst-first, and is already scoped by the caller's
 * 18+ gate, so nothing here has to re-filter.
 *
 * `unknown` is a real state, not a synonym for `ok`: a source installed since
 * the last search has no evidence either way, and presenting that as healthy is
 * how ~100 dead connectors stayed invisible.
 */
export function deriveSourceHealth(
  rows: SourceHealthRow[] | undefined,
): SourceHealth[] {
  const mapped = (rows ?? []).map((row): SourceHealth => {
    const h = row.health;
    const base = {
      source: row.source_id || row.id,
      name: row.name || null,
      consecutiveFailures: h.consecutive_failures,
      demoted: h.demoted,
      lastError: h.last_error,
      lastCheckedAt: h.last_checked_at,
      lastOkAt: h.last_ok_at,
    };
    switch (h.status) {
      case "dead":
        return {
          ...base,
          state: "down",
          message: `Unreachable on the last ${h.consecutive_failures} searches — treat as dead.`,
        };
      case "failing":
        return {
          ...base,
          state: "warn",
          message:
            h.consecutive_failures === 1
              ? "Failed its most recent probe."
              : `Failed its last ${h.consecutive_failures} probes${h.demoted ? " (demoted in search)" : ""}.`,
        };
      case "unknown":
        return {
          ...base,
          state: "unknown",
          message: "Never probed yet, so there is nothing to report.",
        };
      case "ok":
      default:
        return {
          ...base,
          state: "ok",
          message: "Answered its last probe.",
        };
    }
  });

  return mapped.sort(
    (a, b) =>
      STATE_SEVERITY[b.state] - STATE_SEVERITY[a.state] ||
      b.consecutiveFailures - a.consecutiveFailures ||
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
