import { afterEach, describe, expect, it, vi } from "vitest";
import {
  browserAllowsPreload,
  connectionAllowsPreload,
  MAX_PRELOAD_CHAPTERS_AHEAD,
  pagesAheadToWarm,
  PRELOAD_AHEAD_CONTINUOUS,
  PRELOAD_AHEAD_PAGED,
  shouldPreloadNextChapter,
  warmupImageUrls,
} from "./preload";

describe("shouldPreloadNextChapter", () => {
  it("waits until the reader is well into the chapter", () => {
    expect(shouldPreloadNextChapter({ page: 1, pageCount: 40 })).toBe(false);
    expect(shouldPreloadNextChapter({ page: 20, pageCount: 40 })).toBe(false);
    expect(shouldPreloadNextChapter({ page: 24, pageCount: 40 })).toBe(true);
  });

  it("pulls immediately when only a few pages remain", () => {
    expect(shouldPreloadNextChapter({ page: 1, pageCount: 3 })).toBe(true);
    expect(shouldPreloadNextChapter({ page: 38, pageCount: 40 })).toBe(true);
  });

  it("never fires on an empty or unknown chapter", () => {
    expect(shouldPreloadNextChapter({ page: 1, pageCount: 0 })).toBe(false);
    expect(shouldPreloadNextChapter({ page: 0, pageCount: 40 })).toBe(false);
    expect(shouldPreloadNextChapter({ page: Number.NaN, pageCount: 40 })).toBe(false);
  });

  it("honours a caller-supplied threshold", () => {
    expect(shouldPreloadNextChapter({ page: 10, pageCount: 40, ratio: 0.25, tail: 0 })).toBe(
      true,
    );
    expect(shouldPreloadNextChapter({ page: 9, pageCount: 40, ratio: 0.25, tail: 0 })).toBe(
      false,
    );
  });
});

describe("warmupImageUrls", () => {
  const pages = [
    { imageUrl: "/a" },
    { imageUrl: "/b" },
    { imageUrl: "/c" },
    { imageUrl: "/d" },
  ];

  it("warms only the leading pages", () => {
    expect(warmupImageUrls(pages, 2)).toEqual(["/a", "/b"]);
    expect(warmupImageUrls(pages)).toEqual(["/a", "/b", "/c"]);
  });

  it("de-duplicates and tolerates short or empty chapters", () => {
    expect(warmupImageUrls([{ imageUrl: "/a" }, { imageUrl: "/a" }], 3)).toEqual(["/a"]);
    expect(warmupImageUrls([], 3)).toEqual([]);
    expect(warmupImageUrls(pages, 0)).toEqual([]);
  });

  it("stays one chapter ahead", () => {
    expect(MAX_PRELOAD_CHAPTERS_AHEAD).toBeLessThanOrEqual(2);
  });
});

describe("pagesAheadToWarm", () => {
  it("looks further ahead in the continuous strip than in the paged modes", () => {
    expect(pagesAheadToWarm("continuous")).toBe(PRELOAD_AHEAD_CONTINUOUS);
    expect(pagesAheadToWarm("single")).toBe(PRELOAD_AHEAD_PAGED);
    expect(pagesAheadToWarm("double")).toBe(PRELOAD_AHEAD_PAGED);
    expect(pagesAheadToWarm("continuous")).toBeGreaterThan(pagesAheadToWarm("single"));
  });
});

describe("connectionAllowsPreload", () => {
  it("yields to data saver and metered connections", () => {
    expect(connectionAllowsPreload({ saveData: true })).toBe(false);
    expect(connectionAllowsPreload({ type: "cellular" })).toBe(false);
  });

  it("preloads when the connection is unrestricted or unknown", () => {
    expect(connectionAllowsPreload(undefined)).toBe(true);
    expect(connectionAllowsPreload({})).toBe(true);
    expect(connectionAllowsPreload({ type: "wifi", saveData: false })).toBe(true);
  });
});

describe("browserAllowsPreload", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /**
   * The series page and the reader both ask this before spending someone's
   * cellular allowance on a chapter they may never open, so it has to give the
   * same answer `connectionAllowsPreload` would for the live connection.
   */
  it("reads the live connection hint", () => {
    vi.stubGlobal("navigator", { connection: { saveData: true } });
    expect(browserAllowsPreload()).toBe(false);

    vi.stubGlobal("navigator", { connection: { type: "cellular" } });
    expect(browserAllowsPreload()).toBe(false);

    vi.stubGlobal("navigator", { connection: { type: "wifi" } });
    expect(browserAllowsPreload()).toBe(true);
  });

  it("allows preloading when the browser reports nothing", () => {
    vi.stubGlobal("navigator", {});
    expect(browserAllowsPreload()).toBe(true);
  });
});
