import { describe, expect, it } from "vitest";
import {
  describeEntry,
  expiryDueAt,
  formatBytes,
  formatDueIn,
  groupBySeries,
  isFullySaved,
  savePercent,
  savedChapterMedium,
  summariseStorage,
} from "./format";
import type { SavedChapterEntry } from "./types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

function entry(overrides: Partial<SavedChapterEntry> = {}): SavedChapterEntry {
  return {
    key: "chapter:asura:series/solo-levelling:ch/1",
    sourceId: "asura",
    seriesKey: "series/solo-levelling",
    chapterKey: "ch/1",
    title: "Chapter 1",
    seriesTitle: "Solo Levelling",
    pageCount: 40,
    payloadUrl:
      "https://host/api/reader/chapter/manifest?source=asura&series=series%2Fsolo-levelling&chapter=ch%2F1",
    urls: [],
    savedPages: 40,
    bytes: 12 * 1024 * 1024,
    status: "ready",
    failed: 0,
    stale: false,
    savedAt: 1_000,
    lastOpenedAt: null,
    readAt: null,
    medium: "manga",
    ...overrides,
  };
}

/** A saved prose chapter: one payload, no page images. */
function novel(overrides: Partial<SavedChapterEntry> = {}): SavedChapterEntry {
  return entry({
    medium: "novel",
    pageCount: 0,
    savedPages: 0,
    bytes: 14 * 1024,
    ...overrides,
  });
}

describe("formatBytes", () => {
  it("reads like a storage screen", () => {
    expect(formatBytes(0)).toBe("0 MB");
    expect(formatBytes(900)).toBe("900 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(12 * 1024 * 1024)).toBe("12 MB");
    expect(formatBytes(1.5 * 1024 * 1024 * 1024)).toBe("1.5 GB");
  });

  it("does not render nonsense for missing numbers", () => {
    expect(formatBytes(Number.NaN)).toBe("0 MB");
    expect(formatBytes(-5)).toBe("0 MB");
  });
});

describe("describeEntry", () => {
  it("only claims a chapter is saved when every page is on the device", () => {
    expect(describeEntry(entry()).tone).toBe("ready");
    expect(describeEntry(entry({ savedPages: 36, status: "partial" }))).toEqual({
      label: "Incomplete — 36/40 pages",
      tone: "warn",
    });
  });

  it("does not call a chapter ready just because the status says so", () => {
    // Holes are discovered on a train, which is the one place they cannot be
    // fixed, so the count is trusted over the flag.
    expect(describeEntry(entry({ savedPages: 39 })).tone).toBe("warn");
  });

  it("says when the server moved the pages underneath it", () => {
    expect(describeEntry(entry({ stale: true })).tone).toBe("warn");
  });

  it("distinguishes running out of room from failing", () => {
    expect(describeEntry(entry({ status: "paused" })).label).toBe(
      "Paused — device is full",
    );
  });

  it("reports live progress while saving", () => {
    expect(describeEntry(entry({ status: "saving", savedPages: 10 }))).toEqual({
      label: "Saving 10/40",
      tone: "busy",
    });
  });
});

describe("prose entries", () => {
  it("reports bytes rather than a page count it does not have", () => {
    expect(describeEntry(novel({ bytes: 14 * 1024 }))).toEqual({
      label: "Saved · 14 KB",
      tone: "ready",
    });
  });

  it("says it is saving without counting pages", () => {
    expect(describeEntry(novel({ status: "saving" })).label).toBe("Saving");
  });

  it("still flags an interrupted save", () => {
    expect(describeEntry(novel({ status: "partial" })).tone).toBe("warn");
  });
});

describe("isFullySaved", () => {
  it("is true only for a complete, current copy", () => {
    expect(isFullySaved(entry())).toBe(true);
    expect(isFullySaved(entry({ stale: true }))).toBe(false);
    expect(isFullySaved(entry({ savedPages: 39 }))).toBe(false);
    expect(isFullySaved(entry({ status: "saving" }))).toBe(false);
    expect(isFullySaved(null)).toBe(false);
  });
});

describe("savePercent", () => {
  it("clamps to 100", () => {
    expect(savePercent(entry({ pageCount: 10, savedPages: 12 }))).toBe(100);
  });

  it("calls a settled prose chapter complete rather than dividing by zero", () => {
    // A novel is one request and no pages; measuring it against a page count
    // of zero drew an empty bar over a book that was entirely on the device.
    expect(savePercent(novel())).toBe(100);
    expect(savePercent(novel({ status: "saving" }))).toBe(0);
  });
});

describe("savedChapterMedium", () => {
  it("reads the recorded medium", () => {
    expect(savedChapterMedium(entry({ medium: "manga" }))).toBe("manga");
    expect(savedChapterMedium(entry({ medium: "novel", pageCount: 0 }))).toBe("novel");
  });

  it("falls back to the shape for entries saved before the field existed", () => {
    // `isSavableChapter` refuses a manga chapter with no pages, so a
    // page-less entry can only ever be prose.
    expect(savedChapterMedium(entry({ medium: undefined }))).toBe("manga");
    expect(
      savedChapterMedium(entry({ medium: undefined, pageCount: 0, savedPages: 0 })),
    ).toBe("novel");
  });
});

describe("expiry", () => {
  it("has no due date for a chapter that was never finished", () => {
    expect(expiryDueAt(entry({ readAt: null }), 2 * DAY)).toBeNull();
  });

  it("counts from when it was finished", () => {
    expect(expiryDueAt(entry({ readAt: 5_000 }), 2 * DAY)).toBe(5_000 + 2 * DAY);
  });

  it("has no due date when retention is turned off", () => {
    expect(expiryDueAt(entry({ readAt: 5_000 }), null)).toBeNull();
  });

  it("promises only what a closed tab can keep", () => {
    // No timers run while the app is shut, so the wording says "next time you
    // open the app" rather than pretending to a background deletion.
    expect(formatDueIn(1_000, 2_000)).toBe("Deletes next time you open the app");
    expect(formatDueIn(2_000 + 30 * 60_000, 2_000)).toBe("Deletes within the hour");
    expect(formatDueIn(2_000 + 5 * HOUR, 2_000)).toBe("Deletes in about 5 hours");
    expect(formatDueIn(2_000 + 47 * HOUR, 2_000)).toBe("Deletes in about 2 days");
  });
});

describe("groupBySeries", () => {
  it("gathers a series' chapters and adds up what they cost", () => {
    const groups = groupBySeries([
      entry({ key: "a", seriesKey: "series/7", bytes: 100, savedAt: 1 }),
      entry({ key: "b", seriesKey: "series/7", bytes: 50, savedAt: 2 }),
      entry({
        key: "c",
        seriesKey: "series/9",
        seriesTitle: "Omniscient",
        bytes: 10,
        savedAt: 3,
      }),
    ]);
    expect(groups.map((group) => group.seriesKey)).toEqual(["series/9", "series/7"]);
    expect(groups.map((group) => group.id)).toEqual(["asura:series/9", "asura:series/7"]);
    expect(groups[1].bytes).toBe(150);
    expect(groups[1].entries.map((item) => item.key)).toEqual(["a", "b"]);
  });

  it("does not lose a chapter whose series title never arrived", () => {
    const groups = groupBySeries([entry({ seriesTitle: null })]);
    expect(groups[0].seriesTitle).toBe("Unknown series");
  });
});

describe("summariseStorage", () => {
  it("adds up what this feature is accountable for", () => {
    const summary = summariseStorage(
      [entry({ bytes: 100 }), entry({ key: "b", bytes: 50 })],
      { usage: 500, quota: 1_000 },
    );
    expect(summary.chapterBytes).toBe(150);
    expect(summary.chapterCount).toBe(2);
    expect(summary.percentUsed).toBe(50);
    expect(summary.free).toBe(500);
  });

  it("reports no percentage rather than a made-up one", () => {
    // Safari has historically refused to answer; a fabricated bar would be a
    // lie about the one number the user is deciding on.
    const summary = summariseStorage([entry()], null);
    expect(summary.percentUsed).toBeNull();
    expect(summary.free).toBeNull();
    expect(summary.chapterBytes).toBe(12 * 1024 * 1024);
  });

  it("ignores a quota of zero instead of dividing by it", () => {
    expect(summariseStorage([], { usage: 0, quota: 0 }).percentUsed).toBeNull();
  });
});
