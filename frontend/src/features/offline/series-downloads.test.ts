import { describe, expect, it } from "vitest";
import {
  chapterDownloadState,
  needsDownload,
  savedChaptersForSeries,
  savedCount,
  seriesChapterKey,
} from "./series-downloads";
import { describeEntry } from "./format";
import type { SavedChapterEntry } from "./types";

/**
 * A series page and the `/downloads` screen read the same index, so they must
 * never describe the same chapter differently — the precedence below is pinned
 * against `describeEntry` for exactly that reason.
 */

function entry(overrides: Partial<SavedChapterEntry> = {}): SavedChapterEntry {
  return {
    key: "chapter:asura:series/x:ch/1",
    sourceId: "asura",
    seriesKey: "series/x",
    chapterKey: "ch/1",
    title: "Chapter 1",
    seriesTitle: "X",
    pageCount: 10,
    payloadUrl: "https://host/api/reader/chapter/manifest?source=asura",
    urls: [],
    savedPages: 10,
    bytes: 1024,
    status: "ready",
    failed: 0,
    stale: false,
    savedAt: 1,
    lastOpenedAt: null,
    readAt: null,
    ...overrides,
  };
}

describe("savedChaptersForSeries", () => {
  it("keeps only this series' chapters, keyed by chapter key", () => {
    const found = savedChaptersForSeries(
      [
        entry(),
        entry({ chapterKey: "ch/2", key: "chapter:asura:series/x:ch/2" }),
        entry({ seriesKey: "series/other", chapterKey: "ch/1" }),
        entry({ sourceId: "other", chapterKey: "ch/1" }),
      ],
      { sourceId: "asura", seriesKey: "series/x" },
    );
    expect([...found.keys()].sort()).toEqual(["ch/1", "ch/2"]);
  });
});

describe("chapterDownloadState", () => {
  it("is none without an entry", () => {
    expect(chapterDownloadState(null)).toBe("none");
  });

  it("reports saving before anything else", () => {
    expect(chapterDownloadState(entry({ status: "saving", savedPages: 3, stale: true }))).toBe(
      "saving",
    );
  });

  it("reports a full device over staleness", () => {
    expect(chapterDownloadState(entry({ status: "paused", stale: true }))).toBe("paused");
  });

  it("reports staleness over incompleteness", () => {
    expect(chapterDownloadState(entry({ stale: true, savedPages: 4 }))).toBe("stale");
  });

  it("calls a chapter with holes incomplete even when the worker says ready", () => {
    expect(chapterDownloadState(entry({ status: "ready", savedPages: 9 }))).toBe(
      "incomplete",
    );
  });

  it("only says saved when every page is there", () => {
    expect(chapterDownloadState(entry())).toBe("saved");
  });

  it("agrees with the downloads screen about which states are a warning", () => {
    const warned: SavedChapterEntry[] = [
      entry({ status: "paused" }),
      entry({ stale: true }),
      entry({ savedPages: 4 }),
    ];
    for (const row of warned) {
      expect(describeEntry(row).tone).toBe("warn");
      expect(["paused", "stale", "incomplete"]).toContain(chapterDownloadState(row));
    }
    expect(describeEntry(entry()).tone).toBe("ready");
  });
});

describe("needsDownload", () => {
  it("is true for anything short of complete — the worker skips what it has", () => {
    expect(needsDownload(null)).toBe(true);
    expect(needsDownload(entry({ status: "partial", savedPages: 4 }))).toBe(true);
    expect(needsDownload(entry({ status: "paused" }))).toBe(true);
    expect(needsDownload(entry({ stale: true }))).toBe(true);
    expect(needsDownload(entry())).toBe(false);
  });
});

describe("savedCount", () => {
  it("counts only the chapters that are wholly here", () => {
    const saved = new Map([
      ["ch/1", entry()],
      ["ch/2", entry({ chapterKey: "ch/2", savedPages: 3, status: "partial" })],
    ]);
    expect(savedCount([{ key: "ch/1" }, { key: "ch/2" }, { key: "ch/3" }], saved)).toBe(1);
  });
});

describe("seriesChapterKey", () => {
  it("is the key the worker indexes a saved chapter under", () => {
    expect(seriesChapterKey({ sourceId: "asura", seriesKey: "series/x" }, "ch/1")).toBe(
      "chapter:asura:series/x:ch/1",
    );
  });
});
