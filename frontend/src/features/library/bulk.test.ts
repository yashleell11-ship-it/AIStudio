import { describe, expect, it } from "vitest";
import { BULK_CONCURRENCY, type BulkProgress, runBulk, summarizeBulkOutcome } from "./bulk";

/** A worker whose in-flight count can be observed, with manual release. */
function trackingWorker() {
  let inFlight = 0;
  let peak = 0;
  const releases: Array<() => void> = [];
  const started: number[] = [];

  const worker = (item: number) => {
    inFlight += 1;
    peak = Math.max(peak, inFlight);
    started.push(item);
    return new Promise<void>((resolve) => {
      releases.push(() => {
        inFlight -= 1;
        resolve();
      });
    });
  };

  return {
    worker,
    started,
    get peak() {
      return peak;
    },
    get pending() {
      return releases.length;
    },
    releaseAll() {
      // Copy first: resolving lets a queued worker push a new release.
      const batch = releases.splice(0, releases.length);
      for (const release of batch) release();
    },
  };
}

/** Let queued microtasks run so the pool can pick up its next item. */
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await Promise.resolve();
  }
}

describe("runBulk", () => {
  it("never has more than `concurrency` requests in flight", async () => {
    const tracker = trackingWorker();
    const items = Array.from({ length: 50 }, (_, index) => index);

    const run = runBulk(items, tracker.worker, { concurrency: 4 });
    await settle();
    expect(tracker.peak).toBe(4);

    while (tracker.pending > 0) {
      tracker.releaseAll();
      await settle();
    }

    const outcome = await run;
    expect(tracker.peak).toBe(4);
    expect(outcome.succeeded).toHaveLength(50);
  });

  it("starts the next item as soon as one finishes, not in fixed batches", async () => {
    const tracker = trackingWorker();
    const items = [1, 2, 3, 4, 5, 6];

    const run = runBulk(items, tracker.worker, { concurrency: 2 });
    await settle();
    expect(tracker.started).toEqual([1, 2]);

    tracker.releaseAll();
    await settle();
    expect(tracker.started).toEqual([1, 2, 3, 4]);

    while (tracker.pending > 0) {
      tracker.releaseAll();
      await settle();
    }
    await run;
    expect(tracker.started).toEqual(items);
  });

  it("reports progress once per settled item, ending at the total", async () => {
    const progress: BulkProgress[] = [];
    const outcome = await runBulk([1, 2, 3], async () => {}, {
      concurrency: 2,
      onProgress: (value) => progress.push(value),
    });

    expect(progress.map((value) => value.completed)).toEqual([1, 2, 3]);
    expect(progress.every((value) => value.total === 3)).toBe(true);
    expect(outcome.total).toBe(3);
  });

  it("keeps going after a failure and reports which item failed", async () => {
    const outcome = await runBulk([1, 2, 3, 4], async (item) => {
      if (item === 2) throw new Error("404");
    });

    expect(outcome.succeeded).toEqual([1, 3, 4]);
    expect(outcome.failures).toHaveLength(1);
    expect(outcome.failures[0].item).toBe(2);
    expect((outcome.failures[0].error as Error).message).toBe("404");
    expect(outcome.aborted).toBe(false);
  });

  it("counts failures in the progress it reports", async () => {
    const progress: BulkProgress[] = [];
    await runBulk(
      [1, 2],
      async (item) => {
        if (item === 1) throw new Error("nope");
      },
      { concurrency: 1, onProgress: (value) => progress.push(value) },
    );

    expect(progress).toEqual([
      { completed: 1, failed: 1, total: 2 },
      { completed: 2, failed: 1, total: 2 },
    ]);
  });

  it("stops starting work once the signal aborts", async () => {
    const controller = new AbortController();
    const started: number[] = [];

    const outcome = await runBulk(
      [1, 2, 3, 4, 5, 6],
      async (item) => {
        started.push(item);
        if (item === 2) controller.abort();
      },
      { concurrency: 1, signal: controller.signal },
    );

    expect(started).toEqual([1, 2]);
    expect(outcome.aborted).toBe(true);
    expect(outcome.succeeded).toEqual([1, 2]);
  });

  it("does nothing at all for an empty selection", async () => {
    let calls = 0;
    const outcome = await runBulk([], async () => {
      calls += 1;
    });

    expect(calls).toBe(0);
    expect(outcome).toEqual({ total: 0, succeeded: [], failures: [], aborted: false });
  });

  it("never spawns more workers than there are items", async () => {
    const tracker = trackingWorker();
    const run = runBulk([1, 2], tracker.worker, { concurrency: 16 });
    await settle();

    expect(tracker.peak).toBe(2);
    tracker.releaseAll();
    await run;
  });

  it("treats a nonsense concurrency as one worker instead of deadlocking", async () => {
    const outcome = await runBulk([1, 2, 3], async () => {}, { concurrency: 0 });
    expect(outcome.succeeded).toEqual([1, 2, 3]);
  });

  it("defaults to a bounded pool", async () => {
    const tracker = trackingWorker();
    const run = runBulk(Array.from({ length: 200 }, (_, i) => i), tracker.worker);
    await settle();

    expect(tracker.peak).toBe(BULK_CONCURRENCY);

    while (tracker.pending > 0) {
      tracker.releaseAll();
      await settle();
    }
    await run;
  });
});

describe("summarizeBulkOutcome", () => {
  it("reports a clean run", () => {
    expect(
      summarizeBulkOutcome({ total: 3, succeeded: [1, 2, 3], failures: [], aborted: false }, "removed"),
    ).toBe("3 series removed.");
  });

  it("reports partial failure", () => {
    expect(
      summarizeBulkOutcome(
        { total: 3, succeeded: [1, 2], failures: [{ item: 3, error: null }], aborted: false },
        "favourited",
      ),
    ).toBe("2 series favourited, 1 failed.");
  });

  it("does not claim success when everything failed", () => {
    expect(
      summarizeBulkOutcome(
        { total: 1, succeeded: [], failures: [{ item: 1, error: null }], aborted: false },
        "tagged",
      ),
    ).toBe("Nothing tagged — all 1 failed.");
  });

  it("says how many were skipped when the run was stopped", () => {
    expect(
      summarizeBulkOutcome({ total: 10, succeeded: [1, 2], failures: [], aborted: true }, "removed"),
    ).toBe("Stopped: 2 series removed, 8 skipped.");
  });
});
