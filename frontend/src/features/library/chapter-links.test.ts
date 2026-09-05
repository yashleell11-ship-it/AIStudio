import { describe, expect, it } from "vitest";
import { chapterLinksReady } from "./chapter-links";

describe("chapterLinksReady", () => {
  it("links once the source is known to serve pages", () => {
    expect(chapterLinksReady(false)).toBe(true);
  });

  it("links once the source is known to serve prose", () => {
    expect(chapterLinksReady(true)).toBe(true);
  });

  it("waits rather than guessing while the source kind is unknown", () => {
    expect(chapterLinksReady(undefined)).toBe(false);
  });
});
