import { describe, expect, it, afterEach } from "vitest";
import {
  advanceReaderScroll,
  clearChapterScrollPreparation,
  estimateResumeOffset,
  resetChapterScrollPreparationForTests,
  restoreChapterScroll,
  syncChapterScroll,
} from "./scroll-preparation";

describe("estimateResumeOffset", () => {
  it("lands past the page it left off in, plus how far into it", () => {
    expect(
      estimateResumeOffset({
        position: { page: 5, offset: 420 },
        pageCount: 30,
        estimatedOffsetToPage: 1800,
      }),
    ).toBe(2220);
  });

  it("keeps the offset when the reader was still on page one", () => {
    expect(
      estimateResumeOffset({
        position: { page: 1, offset: 420 },
        pageCount: 30,
        estimatedOffsetToPage: 0,
      }),
    ).toBe(420);
  });

  it("resets to the top for a first-time chapter open", () => {
    expect(
      estimateResumeOffset({
        position: null,
        pageCount: 30,
        estimatedOffsetToPage: 1800,
      }),
    ).toBe(0);
  });

  it("ignores a stored position when the chapter has no pages", () => {
    expect(
      estimateResumeOffset({
        position: { page: 5, offset: 420 },
        pageCount: 0,
        estimatedOffsetToPage: 1800,
      }),
    ).toBe(0);
  });

  it("never resolves to a negative offset", () => {
    expect(
      estimateResumeOffset({
        position: { page: 3, offset: -900 },
        pageCount: 30,
        estimatedOffsetToPage: -50,
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

describe("advanceReaderScroll", () => {
  it("moves the container forward by the given distance", () => {
    const element = { scrollTop: 100 } as HTMLElement;
    expect(advanceReaderScroll(element, 50)).toBe(150);
    expect(element.scrollTop).toBe(150);
  });

  it("hands back whatever the browser actually clamped scrollTop to", () => {
    // A real element silently clamps an out-of-range write; a plain object
    // does not, so the setter here stands in for that clamping behaviour —
    // the caller (auto-scroll's pause detection) must trust the read-back,
    // never the requested distance.
    const MAX_SCROLL_TOP = 120;
    let value = 100;
    const element = {
      get scrollTop() {
        return value;
      },
      set scrollTop(next: number) {
        value = Math.min(MAX_SCROLL_TOP, next);
      },
    } as HTMLElement;

    expect(advanceReaderScroll(element, 50)).toBe(MAX_SCROLL_TOP);
  });

  it("supports a negative distance (in case a caller ever needs to reverse)", () => {
    const element = { scrollTop: 100 } as HTMLElement;
    expect(advanceReaderScroll(element, -30)).toBe(70);
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
