import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { naturalPageRatio, readPageRatios, writePageRatios } from "./page-ratios";
import { UNKNOWN_PAGE_ASPECT } from "./page-layout";

describe("remembered page shapes", () => {
  const ALICE = { userId: 1, profileId: 10 };
  const BOB = { userId: 1, profileId: 11 };

  beforeEach(() => {
    installMemoryStorage();
    setStorageScope(null);
  });

  afterEach(() => {
    setStorageScope(null);
    uninstallMemoryStorage();
  });

  it("round-trips a chapter's shapes, holes and all", () => {
    setStorageScope(ALICE);
    writePageRatios("ch-1", [20.37, null, 1.42]);
    expect(readPageRatios("ch-1")).toEqual([20.37, null, 1.42]);
  });

  it("turns a re-read into the same first-frame-exact case a source's own dimensions give", () => {
    setStorageScope(ALICE);
    // A 720x14668 strip lays out at 15,646px in a 768px column. Stored at two
    // decimals it comes back within 2px of that — well under a scroll frame —
    // against the 2,611px the population prior reserves for an unmeasured page.
    writePageRatios("ch-1", [14668 / 720]);
    const remembered = readPageRatios("ch-1")[0];
    expect(remembered).not.toBeNull();
    expect(Math.abs(768 * (remembered as number) - 15645.87)).toBeLessThan(2);
    expect(768 * UNKNOWN_PAGE_ASPECT).toBeLessThan(3000);
  });

  it("is per profile — what you have read is not device-global", () => {
    setStorageScope(ALICE);
    writePageRatios("ch-1", [9.5]);
    setStorageScope(BOB);
    expect(readPageRatios("ch-1")).toEqual([]);
    setStorageScope(ALICE);
    expect(readPageRatios("ch-1")).toEqual([9.5]);
  });

  it("stores nothing at all without an active profile", () => {
    const storage = installMemoryStorage();
    writePageRatios("ch-1", [9.5]);
    expect(storage.keys()).toEqual([]);
    expect(readPageRatios("ch-1")).toEqual([]);
  });

  it("drops trailing holes rather than padding the blob with commas", () => {
    setStorageScope(ALICE);
    writePageRatios("ch-1", [1.5, null, null]);
    expect(readPageRatios("ch-1")).toEqual([1.5]);
    writePageRatios("ch-2", [null, null]);
    expect(readPageRatios("ch-2")).toEqual([]);
  });

  it("refuses ratios that are not a page shape", () => {
    setStorageScope(ALICE);
    writePageRatios("ch-1", [0, 1000, -3, 2]);
    expect(readPageRatios("ch-1")).toEqual([null, null, null, 2]);
  });

  it("caps one chapter's blob so a 4,000-entry listing cannot eat the quota", () => {
    setStorageScope(ALICE);
    writePageRatios("ch-1", Array.from({ length: 5000 }, () => 2));
    expect(readPageRatios("ch-1")).toHaveLength(400);
  });

  it("encodes a page measured out of order as a hole, not a skipped slot", () => {
    setStorageScope(ALICE);
    const sparse: (number | null)[] = [];
    sparse[3] = 4.5;
    writePageRatios("ch-1", sparse);
    expect(readPageRatios("ch-1")).toEqual([null, null, null, 4.5]);
  });

  it("survives a chapter key with the separator in it", () => {
    setStorageScope(ALICE);
    writePageRatios("vol1/ch:2", [3.25]);
    expect(readPageRatios("vol1/ch:2")).toEqual([3.25]);
  });
});

describe("naturalPageRatio", () => {
  it("is the decoded image's shape", () => {
    expect(naturalPageRatio(720, 14668)).toBeCloseTo(20.372);
    expect(naturalPageRatio(800, 1200)).toBe(1.5);
  });

  it("rejects a decode that resolved nothing", () => {
    // A page that failed reports 0x0, and a ratio taken from it would be
    // remembered as this chapter's truth forever.
    expect(naturalPageRatio(0, 0)).toBeNull();
    expect(naturalPageRatio(720, 0)).toBeNull();
    expect(naturalPageRatio(1, 1000)).toBeNull();
  });
});
