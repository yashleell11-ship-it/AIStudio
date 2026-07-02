import { describe, expect, it, afterEach } from "vitest";
import {
  clearChapterScrollPreparation,
  resolveInitialScrollTop,
  resetChapterScrollPreparationForTests,
  restoreChapterScroll,
  syncChapterScroll,
} from "./scroll-preparation";

describe("resolveInitialScrollTop", () => {
  it("restores a saved scroll position when present", () => {
    expect(
      resolveInitialScrollTop({
        savedScroll: 420,
        initialPage: 1,
        pageCount: 30,
        estimatedOffsetToPage: 0,
      }),
    ).toBe(420);
  });

  it("scrolls to the requested page when no saved position exists", () => {
    expect(
      resolveInitialScrollTop({
        savedScroll: null,
        initialPage: 5,
        pageCount: 30,
        estimatedOffsetToPage: 1800,
      }),
    ).toBe(1800);
  });

  it("resets to the top for a first-time chapter open", () => {
    expect(
      resolveInitialScrollTop({
        savedScroll: null,
        initialPage: 1,
        pageCount: 30,
        estimatedOffsetToPage: 0,
      }),
    ).toBe(0);
  });

  it("ignores deep-link page offsets when the chapter has no pages", () => {
    expect(
      resolveInitialScrollTop({
        savedScroll: null,
        initialPage: 5,
        pageCount: 0,
        estimatedOffsetToPage: 1800,
      }),
    ).toBe(0);
  });
});

describe("syncChapterScroll", () => {
  afterEach(() => {
    resetChapterScrollPreparationForTests();
  });

  it("applies the target scroll position once per chapter key and target", () => {
    const element = {
      scrollTop: 900,
    } as HTMLElement;

    syncChapterScroll("chapter-1", element, 0);
    expect(element.scrollTop).toBe(0);

    element.scrollTop = 450;
    syncChapterScroll("chapter-1", element, 0);
    expect(element.scrollTop).toBe(450);
  });

  it("re-syncs when the target offset changes for the same chapter", () => {
    const element = {
      scrollTop: 0,
    } as HTMLElement;

    syncChapterScroll("chapter-1", element, 0);
    syncChapterScroll("chapter-1", element, 2400);

    expect(element.scrollTop).toBe(2400);
  });

  it("allows a new chapter key to be prepared independently", () => {
    const element = {
      scrollTop: 900,
    } as HTMLElement;

    syncChapterScroll("chapter-1", element, 0);
    syncChapterScroll("chapter-2", element, 120);

    expect(element.scrollTop).toBe(120);
  });

  it("can be reset when leaving a chapter", () => {
    const element = {
      scrollTop: 900,
    } as HTMLElement;

    syncChapterScroll("chapter-1", element, 0);
    clearChapterScrollPreparation("chapter-1");
    syncChapterScroll("chapter-1", element, 200);

    expect(element.scrollTop).toBe(200);
  });
});

describe("restoreChapterScroll", () => {
  it("re-applies a saved offset after layout clamping", () => {
    const element = {
      scrollTop: 0,
    } as HTMLElement;

    expect(restoreChapterScroll(element, 1800)).toBe(true);
    expect(element.scrollTop).toBe(1800);
  });

  it("does not override user scrolling at the top", () => {
    const element = {
      scrollTop: 0,
    } as HTMLElement;

    expect(restoreChapterScroll(element, 0)).toBe(false);
    expect(element.scrollTop).toBe(0);
  });
});
