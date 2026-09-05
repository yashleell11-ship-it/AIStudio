import { describe, expect, it, vi } from "vitest";
import {
  describeRun,
  planDownload,
  runDownloadQueue,
  type SaveOutcome,
} from "./download-queue";
import type { SelectableChapter } from "./chapter-selection";

/**
 * The queue's two jobs are sequencing and honesty: one chapter in the worker at
 * a time (each is already fetching four images), and a run that ran out of room
 * must say so rather than report the chapters it never attempted as done.
 */

function chapter(number: number, saved = false): SelectableChapter {
  return { key: `ch/${number}`, number, saved, read: false };
}

describe("planDownload", () => {
  it("is the selection in reading order, whatever order the page listed", () => {
    const rows = [chapter(3), chapter(1), chapter(2)];
    expect(planDownload(rows, new Set(["ch/3", "ch/1", "ch/2"]))).toEqual([
      "ch/1",
      "ch/2",
      "ch/3",
    ]);
  });

  it("drops chapters already fully on the device", () => {
    const rows = [chapter(1), chapter(2, true), chapter(3)];
    expect(planDownload(rows, new Set(["ch/1", "ch/2", "ch/3"]))).toEqual([
      "ch/1",
      "ch/3",
    ]);
  });

  it("ignores selected keys the list no longer holds", () => {
    expect(planDownload([chapter(1)], new Set(["ch/1", "ch/99"]))).toEqual(["ch/1"]);
  });
});

describe("runDownloadQueue", () => {
  it("never has two chapters in the worker at once", async () => {
    let inFlight = 0;
    let peak = 0;
    await runDownloadQueue(["a", "b", "c"], {
      save: async () => {
        inFlight += 1;
        peak = Math.max(peak, inFlight);
        await Promise.resolve();
        inFlight -= 1;
        return "saved";
      },
    });
    expect(peak).toBe(1);
  });

  it("tallies each outcome", async () => {
    const outcomes: Record<string, SaveOutcome> = {
      a: "saved",
      b: "incomplete",
      c: "failed",
      d: "saved",
    };
    const run = await runDownloadQueue(["a", "b", "c", "d"], {
      save: async (key) => outcomes[key],
    });
    expect(run).toMatchObject({
      requested: 4,
      saved: 2,
      incomplete: 1,
      failed: 1,
      skipped: 0,
      outOfSpace: false,
      cancelled: false,
    });
  });

  it("stops at the first paused chapter — the rest would only pause too", async () => {
    const attempted: string[] = [];
    const run = await runDownloadQueue(["a", "b", "c", "d"], {
      save: async (key) => {
        attempted.push(key);
        return key === "b" ? "paused" : "saved";
      },
    });
    expect(attempted).toEqual(["a", "b"]);
    expect(run).toMatchObject({ saved: 1, outOfSpace: true, skipped: 2 });
  });

  it("counts a throwing save as a failure and carries on", async () => {
    const run = await runDownloadQueue(["a", "b"], {
      save: async (key) => {
        if (key === "a") throw new Error("no manifest");
        return "saved";
      },
    });
    expect(run).toMatchObject({ saved: 1, failed: 1 });
  });

  it("stops before the next chapter when aborted, and says what it skipped", async () => {
    const controller = new AbortController();
    const run = await runDownloadQueue(["a", "b", "c"], {
      signal: controller.signal,
      save: async () => {
        controller.abort();
        return "saved";
      },
    });
    expect(run).toMatchObject({ saved: 1, cancelled: true, skipped: 2 });
  });

  it("offers the warm everything still to come, current chapter first", async () => {
    const seen: string[][] = [];
    await runDownloadQueue(["a", "b", "c"], {
      save: async () => "saved",
      prepare: async (upcoming) => {
        seen.push([...upcoming]);
      },
    });
    expect(seen).toEqual([["a", "b", "c"], ["b", "c"], ["c"]]);
  });

  it("saves the chapter anyway when the warm fails", async () => {
    const save = vi.fn(async () => "saved" as SaveOutcome);
    const run = await runDownloadQueue(["a"], {
      save,
      prepare: async () => {
        throw new Error("429");
      },
    });
    expect(save).toHaveBeenCalledOnce();
    expect(run.saved).toBe(1);
  });
});

describe("describeRun", () => {
  const base = {
    requested: 10,
    saved: 0,
    incomplete: 0,
    failed: 0,
    skipped: 0,
    outOfSpace: false,
    cancelled: false,
  };

  it("names both numbers when the device filled up mid-run", () => {
    const summary = describeRun(
      { ...base, saved: 6, skipped: 4, outOfSpace: true },
      120 * 1024 * 1024,
    );
    expect(summary.tone).toBe("warn");
    expect(summary.label).toContain("6 of 10 downloaded");
    expect(summary.label).toContain("4 not started");
    expect(summary.label).toContain("120 MB");
  });

  it("never counts a chapter with holes as downloaded, however the run ended", () => {
    const stopped = describeRun(
      { ...base, saved: 4, incomplete: 2, skipped: 4, outOfSpace: true },
      null,
    );
    expect(stopped.label).toContain("4 of 10 downloaded");
    expect(stopped.label).toContain("2 with missing pages");

    const cancelled = describeRun(
      { ...base, saved: 4, incomplete: 1, failed: 1, skipped: 4, cancelled: true },
      null,
    );
    expect(cancelled.label).toContain("4 of 10 downloaded");
    expect(cancelled.label).toContain("1 with missing pages");
    expect(cancelled.label).toContain("1 failed");
    expect(cancelled.label).toContain("4 not started");
  });

  it("omits the free-space figure when the browser will not report one", () => {
    const summary = describeRun({ ...base, saved: 6, skipped: 4, outOfSpace: true }, null);
    expect(summary.label).not.toContain("free");
  });

  it("does not let holes hide behind the successes", () => {
    const summary = describeRun({ ...base, saved: 7, incomplete: 2, failed: 1 }, null);
    expect(summary.tone).toBe("warn");
    expect(summary.label).toContain("7 of 10 downloaded");
    expect(summary.label).toContain("2 with missing pages");
    expect(summary.label).toContain("1 failed");
  });

  it("is quiet when everything landed", () => {
    expect(describeRun({ ...base, saved: 10 }, null)).toEqual({
      label: "10 chapters downloaded.",
      tone: "ready",
    });
  });

  it("says so when there was nothing to do", () => {
    expect(describeRun({ ...base, requested: 0 }, null).tone).toBe("ready");
  });
});
