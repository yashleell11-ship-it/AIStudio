import { describe, expect, it } from "vitest";
import {
  EMPTY_CHAPTER_SELECTION,
  addChapters,
  everyChapter,
  extendChapterSelection,
  nextChapters,
  readingOrder,
  toggleChapter,
  unreadChapters,
  type SelectableChapter,
} from "./chapter-selection";

/**
 * The range helpers are the thing being built: "select ten rows by hand" is
 * what they replace, so getting "which ten" wrong is the whole bug.
 */

function chapter(
  number: number | null,
  overrides: Partial<SelectableChapter> = {},
): SelectableChapter {
  return {
    key: `ch/${number ?? "x"}`,
    number,
    saved: false,
    read: false,
    ...overrides,
  };
}

/** Chapters 1..5, as a series page in newest-first order would hand them over. */
function series(): SelectableChapter[] {
  return [chapter(5), chapter(4), chapter(3), chapter(2), chapter(1)];
}

describe("readingOrder", () => {
  it("runs forwards whatever order the page listed them in", () => {
    expect(readingOrder(series()).map((row) => row.number)).toEqual([1, 2, 3, 4, 5]);
  });

  it("puts unnumbered chapters last, keeping their listed order", () => {
    const rows = [
      { ...chapter(null), key: "extra-b" },
      chapter(2),
      { ...chapter(null), key: "extra-a" },
      chapter(1),
    ];
    expect(readingOrder(rows).map((row) => row.key)).toEqual([
      "ch/1",
      "ch/2",
      "extra-b",
      "extra-a",
    ]);
  });
});

describe("nextChapters", () => {
  it("takes the next N forwards from the first unread, not off the top of the list", () => {
    const rows = series().map((row) =>
      row.number != null && row.number <= 2 ? { ...row, read: true } : row,
    );
    expect(nextChapters(rows, 2)).toEqual(["ch/3", "ch/4"]);
  });

  it("starts at the beginning when nothing has been read", () => {
    expect(nextChapters(series(), 3)).toEqual(["ch/1", "ch/2", "ch/3"]);
  });

  it("skips what is already on the device rather than counting it", () => {
    const rows = series().map((row) =>
      row.number === 2 ? { ...row, saved: true } : row,
    );
    expect(nextChapters(rows, 2)).toEqual(["ch/1", "ch/3"]);
  });

  it("yields nothing once the reader is caught up", () => {
    expect(nextChapters(series().map((row) => ({ ...row, read: true })), 10)).toEqual([]);
  });

  it("yields nothing for a non-positive count", () => {
    expect(nextChapters(series(), 0)).toEqual([]);
  });
});

describe("unreadChapters", () => {
  it("is everything unfinished and not already saved, in reading order", () => {
    const rows = [
      chapter(3),
      { ...chapter(2), read: true },
      { ...chapter(1), saved: true },
      chapter(4),
    ];
    expect(unreadChapters(rows)).toEqual(["ch/3", "ch/4"]);
  });
});

describe("everyChapter", () => {
  it("is the whole series minus what is already here", () => {
    const rows = series().map((row) =>
      row.number === 3 ? { ...row, saved: true } : row,
    );
    expect(everyChapter(rows)).toEqual(["ch/1", "ch/2", "ch/4", "ch/5"]);
  });

  it("includes finished chapters — a re-read is still worth having offline", () => {
    expect(everyChapter(series().map((row) => ({ ...row, read: true })))).toHaveLength(5);
  });
});

describe("addChapters", () => {
  it("adds to what is already ticked instead of replacing it", () => {
    const first = toggleChapter(EMPTY_CHAPTER_SELECTION, "ch/9");
    const merged = addChapters(first, ["ch/1", "ch/2"]);
    expect([...merged.ids].sort()).toEqual(["ch/1", "ch/2", "ch/9"]);
    expect(merged.anchor).toBe("ch/9");
  });

  it("leaves the selection untouched when there is nothing to add", () => {
    const state = toggleChapter(EMPTY_CHAPTER_SELECTION, "ch/9");
    expect(addChapters(state, [])).toBe(state);
  });

  it("anchors on the first added key when nothing has been clicked yet", () => {
    expect(addChapters(EMPTY_CHAPTER_SELECTION, ["ch/4"]).anchor).toBe("ch/4");
  });
});

describe("shift-click over chapter keys", () => {
  it("takes the displayed range between the anchor and the click", () => {
    const order = ["ch/5", "ch/4", "ch/3", "ch/2", "ch/1"];
    const anchored = toggleChapter(EMPTY_CHAPTER_SELECTION, "ch/4");
    const ranged = extendChapterSelection(anchored, "ch/2", order);
    expect([...ranged.ids].sort()).toEqual(["ch/2", "ch/3", "ch/4"]);
  });
});
