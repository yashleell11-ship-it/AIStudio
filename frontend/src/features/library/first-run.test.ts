import { describe, expect, it } from "vitest";
import { shouldShowFirstRunHint } from "./first-run";

describe("shouldShowFirstRunHint", () => {
  it("shows on an ordinary screen when nothing is followed yet", () => {
    expect(
      shouldShowFirstRunHint({ followedCount: 0, pathname: "/updates" }),
    ).toBe(true);
  });

  it("stays hidden while the follow count is still unknown", () => {
    expect(
      shouldShowFirstRunHint({ followedCount: null, pathname: "/updates" }),
    ).toBe(false);
  });

  it("disappears the moment anything is followed", () => {
    expect(
      shouldShowFirstRunHint({ followedCount: 1, pathname: "/updates" }),
    ).toBe(false);
    expect(
      shouldShowFirstRunHint({ followedCount: 12, pathname: "/updates" }),
    ).toBe(false);
  });

  it("stays permanently gone — there is no dismissal to reset, only the count", () => {
    // Once follows exist the caller never even asks with followedCount: 0
    // again for this account; verify the function has no other state a
    // regression could reintroduce.
    const withFollows = shouldShowFirstRunHint({ followedCount: 3, pathname: "/downloads" });
    const backToZero = shouldShowFirstRunHint({ followedCount: 0, pathname: "/downloads" });
    expect(withFollows).toBe(false);
    // Unfollowing everything legitimately brings it back — the function has
    // no memory, which is what "no nagging, no stale dismiss flag" means here.
    expect(backToZero).toBe(true);
  });

  it("suppresses on the Library shelf, which already has its own full empty state", () => {
    expect(shouldShowFirstRunHint({ followedCount: 0, pathname: "/library" })).toBe(false);
  });

  it("suppresses on Sources and its subpaths, the hint's own destination", () => {
    expect(shouldShowFirstRunHint({ followedCount: 0, pathname: "/sources" })).toBe(false);
    expect(
      shouldShowFirstRunHint({ followedCount: 0, pathname: "/sources/mangadex" }),
    ).toBe(false);
  });

  it("shows on every other screen a fresh account might land on", () => {
    for (const pathname of [
      "/library/browse",
      "/library/collections",
      "/library/statistics",
      "/library/recommendations",
      "/library/history",
      "/library/bookmarks",
      "/downloads",
      "/updates",
      "/search",
      "/ocr",
      "/more",
    ]) {
      expect(shouldShowFirstRunHint({ followedCount: 0, pathname })).toBe(true);
    }
  });
});
