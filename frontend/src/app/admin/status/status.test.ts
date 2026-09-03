import { describe, expect, it } from "vitest";
import { describeCheckSchedule } from "@/features/updates/notifications";
import type { UpdateRun, UpdateSettings } from "@/features/updates/types";
import { ApiError } from "@/types/api";
import type { SourceHealthRow } from "./api";
import {
  deriveBackendHealth,
  deriveCheckerHealth,
  deriveSourceHealth,
  deriveSystemSummary,
  worstState,
  type HealthState,
} from "./status";

function run(overrides: Partial<UpdateRun> = {}): UpdateRun {
  return {
    id: 1,
    trigger: "scheduled",
    status: "completed",
    series_checked: 4,
    new_chapters_found: 0,
    error: null,
    started_at: "2026-07-28T11:00:00Z",
    finished_at: "2026-07-28T11:00:10Z",
    ...overrides,
  };
}

function settings(overrides: Partial<UpdateSettings> = {}): UpdateSettings {
  return {
    enabled: true,
    check_interval_minutes: 60,
    notify_enabled: true,
    check_on_startup: true,
    last_run_at: "2026-07-28T11:30:00Z",
    ...overrides,
  };
}

function sourceRow(
  source_id: string,
  health: Partial<SourceHealthRow["health"]> = {},
  name = source_id,
): SourceHealthRow {
  return {
    id: source_id,
    source_id,
    name,
    mature: false,
    health: {
      status: "ok",
      consecutive_failures: 0,
      demoted: false,
      last_ok_at: "2026-07-28T11:00:00Z",
      last_error_at: null,
      last_error: null,
      last_checked_at: "2026-07-28T11:00:00Z",
      ...health,
    },
  };
}

const NOON = Date.parse("2026-07-28T12:00:00Z");

describe("worstState", () => {
  it("is ok for an empty list", () => {
    expect(worstState([])).toBe("ok");
  });

  it("ranks down over warn over unknown over ok", () => {
    expect(worstState(["ok", "unknown"])).toBe("unknown");
    expect(worstState(["unknown", "warn"])).toBe("warn");
    expect(worstState(["warn", "down"])).toBe("down");
    expect(worstState(["down", "ok", "warn", "unknown"])).toBe("down");
  });
});

describe("deriveBackendHealth", () => {
  it("is unknown while the probe is in flight", () => {
    const health = deriveBackendHealth({
      status: undefined,
      error: null,
      isLoading: true,
    });

    expect(health.state).toBe("unknown");
    expect(health.reachable).toBe(false);
  });

  it("reports a transport failure as unreachable, not as an error response", () => {
    const health = deriveBackendHealth({
      status: undefined,
      error: new ApiError(0, {
        code: "network_error",
        message: "Could not reach the server.",
      }),
      isLoading: false,
    });

    expect(health.state).toBe("down");
    expect(health.reachable).toBe(false);
    expect(health.message).toContain("did not answer");
  });

  it("surfaces the server's own message when it answered with an error", () => {
    const health = deriveBackendHealth({
      status: undefined,
      error: new ApiError(503, {
        code: "unavailable",
        message: "database is locked",
      }),
      isLoading: false,
    });

    expect(health.state).toBe("down");
    expect(health.message).toContain("database is locked");
  });

  it("reports name and version when the probe succeeds", () => {
    const health = deriveBackendHealth({
      status: { status: "online", name: "ManhwaManiacs", version: "1.4.2" },
      error: null,
      isLoading: false,
    });

    expect(health).toMatchObject({
      state: "ok",
      reachable: true,
      version: "1.4.2",
    });
  });

  it("warns when the API answers with a status other than online", () => {
    const health = deriveBackendHealth({
      status: { status: "degraded", name: "ManhwaManiacs", version: "1.4.2" },
      error: null,
      isLoading: false,
    });

    expect(health.state).toBe("warn");
    expect(health.message).toContain("degraded");
  });
});

describe("deriveCheckerHealth", () => {
  const schedule = (overrides: Partial<UpdateSettings> = {}) =>
    describeCheckSchedule(settings(overrides), NOON);

  it("is unknown before settings arrive", () => {
    const health = deriveCheckerHealth({
      settings: undefined,
      runs: undefined,
      schedule: null,
      isLoading: true,
    });

    expect(health.state).toBe("unknown");
    expect(health.lastRun).toBeNull();
  });

  it("warns when automatic checks are switched off", () => {
    const health = deriveCheckerHealth({
      settings: settings({ enabled: false }),
      runs: [run()],
      schedule: schedule({ enabled: false }),
      isLoading: false,
    });

    expect(health.state).toBe("warn");
    expect(health.message).toContain("switched off");
  });

  it("is down while the newest runs are failures, and counts the streak", () => {
    const health = deriveCheckerHealth({
      settings: settings(),
      runs: [
        run({ id: 3, status: "failed", error: "connector registry unavailable" }),
        run({ id: 2, status: "failed", error: "connector registry unavailable" }),
        run({ id: 1, status: "completed" }),
      ],
      schedule: schedule(),
      isLoading: false,
    });

    expect(health.state).toBe("down");
    expect(health.consecutiveFailures).toBe(2);
    expect(health.failedRuns).toHaveLength(2);
    expect(health.message).toContain("last 2 update checks failed");
  });

  it("does not count older failures once a newer run succeeded", () => {
    const health = deriveCheckerHealth({
      settings: settings(),
      runs: [run({ id: 3, status: "completed" }), run({ id: 2, status: "failed" })],
      schedule: schedule(),
      isLoading: false,
    });

    expect(health.consecutiveFailures).toBe(0);
    expect(health.state).toBe("ok");
    expect(health.failedRuns).toHaveLength(1);
  });

  it("ignores an in-progress run when measuring the failure streak", () => {
    const health = deriveCheckerHealth({
      settings: settings(),
      runs: [
        run({ id: 4, status: "running", finished_at: null }),
        run({ id: 3, status: "completed" }),
      ],
      schedule: schedule(),
      isLoading: false,
    });

    expect(health.consecutiveFailures).toBe(0);
    expect(health.runningRun?.id).toBe(4);
    expect(health.state).toBe("ok");
  });

  it("warns when no check has ever finished", () => {
    const health = deriveCheckerHealth({
      settings: settings({ last_run_at: null }),
      runs: [],
      schedule: schedule({ last_run_at: null }),
      isLoading: false,
    });

    expect(health.state).toBe("warn");
    expect(health.message).toContain("No update check has finished");
  });

  it("warns when the next check is more than a whole interval late", () => {
    const health = deriveCheckerHealth({
      settings: settings({ last_run_at: "2026-07-28T08:00:00Z" }),
      runs: [run()],
      schedule: schedule({ last_run_at: "2026-07-28T08:00:00Z" }),
      isLoading: false,
    });

    expect(health.state).toBe("warn");
    expect(health.message).toContain("180 minutes ago");
  });

  it("is ok when the last run completed and the schedule is current", () => {
    const health = deriveCheckerHealth({
      settings: settings(),
      runs: [run()],
      schedule: schedule(),
      isLoading: false,
    });

    expect(health.state).toBe("ok");
    expect(health.lastRun?.id).toBe(1);
  });
});

describe("deriveSourceHealth", () => {
  it("returns an empty list when nothing is installed", () => {
    expect(deriveSourceHealth(undefined)).toEqual([]);
    expect(deriveSourceHealth([])).toEqual([]);
  });

  it("maps an answering source to ok", () => {
    const rows = deriveSourceHealth([sourceRow("mangadex", { status: "ok" }, "MangaDex")]);

    expect(rows[0]).toMatchObject({
      source: "mangadex",
      name: "MangaDex",
      state: "ok",
    });
  });

  it("maps a failing source to warn and surfaces the streak + error", () => {
    const rows = deriveSourceHealth([
      sourceRow("flaky", {
        status: "failing",
        consecutive_failures: 2,
        last_error: "HTTP 522",
        demoted: false,
      }),
    ]);

    expect(rows[0].state).toBe("warn");
    expect(rows[0].consecutiveFailures).toBe(2);
    expect(rows[0].lastError).toBe("HTTP 522");
    expect(rows[0].message).toContain("last 2 probes");
  });

  it("maps a dead source to down", () => {
    const rows = deriveSourceHealth([
      sourceRow("gone", {
        status: "dead",
        consecutive_failures: 10,
        last_error: "NXDOMAIN",
        demoted: true,
      }),
    ]);

    expect(rows[0].state).toBe("down");
    expect(rows[0].demoted).toBe(true);
    expect(rows[0].message).toContain("dead");
  });

  it("maps a never-probed source to unknown, never to healthy", () => {
    const rows = deriveSourceHealth([
      sourceRow("fresh", {
        status: "unknown",
        last_ok_at: null,
        last_checked_at: null,
      }),
    ]);

    expect(rows[0].state).toBe("unknown");
  });

  it("sorts the most broken sources first", () => {
    const rows = deriveSourceHealth([
      sourceRow("healthy", { status: "ok" }),
      sourceRow("dead", { status: "dead", consecutive_failures: 10 }),
      sourceRow("failing", { status: "failing", consecutive_failures: 3 }),
      sourceRow("fresh", { status: "unknown" }),
    ]);

    expect(rows.map((row) => row.source)).toEqual([
      "dead",
      "failing",
      "fresh",
      "healthy",
    ]);
  });
});

describe("deriveSystemSummary", () => {
  const healthy = (state: HealthState = "ok") => ({
    backend: deriveBackendHealth({
      status: { status: "online", name: "ManhwaManiacs", version: "1.0.0" },
      error: null,
      isLoading: false,
    }),
    checker: deriveCheckerHealth({
      settings: settings(),
      runs: [run()],
      schedule: describeCheckSchedule(settings(), NOON),
      isLoading: false,
    }),
    sources: deriveSourceHealth(
      state === "ok"
        ? [sourceRow("mangadex", { status: "ok" }, "MangaDex")]
        : [
            sourceRow(
              "mangadex",
              { status: "dead", consecutive_failures: 10, last_error: "boom" },
              "MangaDex",
            ),
          ],
    ),
  });

  it("is healthy with no problems when every part is ok", () => {
    const summary = deriveSystemSummary(healthy());

    expect(summary.state).toBe("ok");
    expect(summary.problems).toEqual([]);
    expect(summary.headline).toBe("Everything is healthy.");
  });

  it("escalates to the worst part and lists every problem", () => {
    const summary = deriveSystemSummary(healthy("down"));

    expect(summary.state).toBe("down");
    expect(summary.problems).toHaveLength(1);
    expect(summary.problems.some((problem) => problem.includes("MangaDex"))).toBe(
      true,
    );
  });

  it("reports unknown, not healthy, while data is still arriving", () => {
    const summary = deriveSystemSummary({
      backend: deriveBackendHealth({
        status: undefined,
        error: null,
        isLoading: true,
      }),
      checker: deriveCheckerHealth({
        settings: undefined,
        runs: undefined,
        schedule: null,
        isLoading: true,
      }),
      sources: [],
    });

    expect(summary.state).toBe("unknown");
    expect(summary.headline).toBe("Still gathering status…");
    expect(summary.problems).toEqual([]);
  });
});
