import { describe, expect, it } from "vitest";
import {
  buildStripRows,
  chapterFirstPageRow,
  chapterIndexOf,
  chapterLastRow,
  findStripRow,
  freezeChapterHeight,
  nextChapterLabelFor,
  releasedChapterKeys,
  shouldExtendAhead,
  shouldPersistFrozenHeights,
  stripChapterLabel,
  stripPositionAt,
  type StripChapter,
} from "./strip";

function chapter(key: string, pageCount: number, number: number | null): StripChapter {
  return {
    sourceId: "asurascans",
    seriesKey: "series/one",
    chapterKey: key,
    chapterNumber: number,
    title: number != null ? `Chapter ${number}` : "Chapter",
    pageCount,
    previousChapterKey: null,
    nextChapterKey: null,
    pages: Array.from({ length: pageCount }, (_, index) => ({
      id: `${key}:${index + 1}`,
      number: index + 1,
      imageUrl: `/img/${key}/${index + 1}`,
      width: null,
      height: null,
    })),
  };
}

const one = chapter("ch-1", 3, 1);
const two = chapter("ch-2", 2, 2);
const three = chapter("ch-3", 2, 3);

describe("buildStripRows", () => {
  it("lays one chapter out with no divider above it", () => {
    const rows = buildStripRows([one]);
    expect(rows).toHaveLength(3);
    expect(rows.every((row) => row.kind === "page")).toBe(true);
  });

  it("puts a divider before every chapter after the first", () => {
    const rows = buildStripRows([one, two, three]);
    expect(rows.map((row) => row.kind)).toEqual([
      "page",
      "page",
      "page",
      "divider",
      "page",
      "page",
      "divider",
      "page",
      "page",
    ]);
  });

  it("numbers pages within their own chapter, not across the strip", () => {
    const rows = buildStripRows([one, two]);
    const pages = rows.filter((row) => row.kind === "page");
    expect(pages.map((row) => `${row.chapterKey}#${row.pageNumber}`)).toEqual([
      "ch-1#1",
      "ch-1#2",
      "ch-1#3",
      "ch-2#1",
      "ch-2#2",
    ]);
  });

  it("names the chapter being entered on the divider", () => {
    const rows = buildStripRows([one, two]);
    const divider = rows.find((row) => row.kind === "divider");
    expect(divider?.chapterKey).toBe("ch-2");
    expect(divider?.kind === "divider" && divider.label).toBe("Chapter 2");
  });

  it("gives every row a key that survives a prepend", () => {
    const before = buildStripRows([two, three]);
    const after = buildStripRows([one, two, three]);
    const beforeKeys = before.map((row) => row.key);
    const afterKeys = after.map((row) => row.key);
    // Every key the strip already had is still present and still unique, so the
    // virtualizer's per-key measurements survive the index shift.
    for (const key of beforeKeys) {
      expect(afterKeys).toContain(key);
    }
    expect(new Set(afterKeys).size).toBe(afterKeys.length);
  });

  it("replaces a released chapter's pages with one spacer of its height", () => {
    const rows = buildStripRows([one, two], {
      released: new Set(["ch-1"]),
      releasedHeight: () => 4200,
    });
    expect(rows[0]).toMatchObject({ kind: "spacer", chapterKey: "ch-1", height: 4200 });
    expect(rows.filter((row) => row.chapterKey === "ch-1")).toHaveLength(1);
    // The chapter is still announced and still countable.
    expect(rows[0].pageCount).toBe(3);
  });

  it("treats an unmeasured released chapter as zero rather than NaN", () => {
    const rows = buildStripRows([one], { released: new Set(["ch-1"]) });
    expect(rows[0]).toMatchObject({ kind: "spacer", height: 0 });
  });
});

describe("stripPositionAt", () => {
  const rows = buildStripRows([one, two]);

  it("reports a page against its own chapter", () => {
    expect(stripPositionAt(rows, 4)).toEqual({
      chapterKey: "ch-2",
      pageNumber: 1,
      pageCount: 2,
    });
  });

  it("reports a divider as page one of the chapter being entered", () => {
    expect(stripPositionAt(rows, 3)).toEqual({
      chapterKey: "ch-2",
      pageNumber: 1,
      pageCount: 2,
    });
  });

  it("has nothing to say about a row that does not exist", () => {
    expect(stripPositionAt(rows, 99)).toBeNull();
    expect(stripPositionAt([], 0)).toBeNull();
  });
});

describe("findStripRow", () => {
  const rows = buildStripRows([one, two]);

  it("finds a page by chapter and page number", () => {
    expect(findStripRow(rows, "ch-1", 2)).toBe(1);
    expect(findStripRow(rows, "ch-2", 2)).toBe(5);
  });

  it("falls back to the chapter's first row for an out-of-range page", () => {
    // The divider is ch-2's first row, so a seek past its end still lands in it.
    expect(findStripRow(rows, "ch-2", 99)).toBe(3);
  });

  it("falls back to a released chapter's spacer", () => {
    const released = buildStripRows([one, two], {
      released: new Set(["ch-1"]),
      releasedHeight: () => 100,
    });
    expect(findStripRow(released, "ch-1", 2)).toBe(0);
  });

  it("answers -1 for a chapter that is not in the strip", () => {
    expect(findStripRow(rows, "ch-9", 1)).toBe(-1);
  });
});

describe("chapter row lookups", () => {
  const rows = buildStripRows([one, two]);

  it("finds the first page row, skipping the divider", () => {
    expect(chapterFirstPageRow(rows, "ch-2")).toBe(4);
    expect(chapterFirstPageRow(rows, "ch-9")).toBe(-1);
  });

  it("finds the last row of a chapter", () => {
    expect(chapterLastRow(rows, "ch-1")).toBe(2);
    expect(chapterLastRow(rows, "ch-2")).toBe(5);
    expect(chapterLastRow(rows, "ch-9")).toBe(-1);
  });

  it("locates a chapter in the loaded list", () => {
    expect(chapterIndexOf([one, two], "ch-2")).toBe(1);
    expect(chapterIndexOf([one, two], "ch-9")).toBe(-1);
  });
});

describe("shouldExtendAhead", () => {
  it("pulls the next chapter as soon as the current one is the last loaded", () => {
    expect(shouldExtendAhead(0, 1, 1)).toBe(true);
    expect(shouldExtendAhead(0, 2, 1)).toBe(false);
    expect(shouldExtendAhead(1, 2, 1)).toBe(true);
  });

  it("keeps a deeper queue when asked for one", () => {
    expect(shouldExtendAhead(0, 3, 3)).toBe(true);
    expect(shouldExtendAhead(0, 4, 3)).toBe(false);
  });

  it("says nothing about an empty or unknown strip", () => {
    expect(shouldExtendAhead(-1, 3, 1)).toBe(false);
    expect(shouldExtendAhead(0, 0, 1)).toBe(false);
  });
});

describe("releasedChapterKeys", () => {
  const many = Array.from({ length: 9 }, (_, index) =>
    chapter(`ch-${index + 1}`, 2, index + 1),
  );

  it("keeps the neighbourhood of the active chapter rendered", () => {
    expect([...releasedChapterKeys(many, 4, 2)]).toEqual([
      "ch-1",
      "ch-2",
      "ch-8",
      "ch-9",
    ]);
  });

  it("releases nothing in a strip smaller than the radius", () => {
    expect(releasedChapterKeys([one, two, three], 1, 2).size).toBe(0);
  });

  it("releases nothing while the active chapter is unknown", () => {
    expect(releasedChapterKeys(many, -1, 2).size).toBe(0);
  });
});

describe("stripChapterLabel", () => {
  it("uses the manifest title", () => {
    expect(stripChapterLabel(one)).toBe("Chapter 1");
  });

  it("never renders an empty divider", () => {
    expect(stripChapterLabel({ ...one, title: "   " })).toBe("Chapter");
  });
});

describe("freezeChapterHeight", () => {
  const measured = new Map([
    ["ch-1:1", 1400],
    ["ch-1:2", 1600],
  ]);
  const estimate = () => 1500;

  it("adds up what the pages actually occupied", () => {
    const { total } = freezeChapterHeight(one, measured, estimate);
    expect(total).toBe(1400 + 1600 + 1500);
  });

  it("freezes a height for every row, so expanding restores the same total", () => {
    const { total, frozen } = freezeChapterHeight(one, measured, estimate);
    expect(frozen.map(([key]) => key)).toEqual(["ch-1:1", "ch-1:2", "ch-1:3"]);
    // The invariant the whole releasing scheme rests on: the spacer is exactly
    // as tall as the rows it replaced, and those rows come back the same size.
    expect(frozen.reduce((sum, [, height]) => sum + height, 0)).toBe(total);
  });

  it("keeps every measured height it was given", () => {
    const { frozen } = freezeChapterHeight(one, measured, estimate);
    expect(new Map(frozen).get("ch-1:1")).toBe(1400);
    expect(new Map(frozen).get("ch-1:3")).toBe(1500);
  });

  it("never freezes a negative height", () => {
    const { total } = freezeChapterHeight(one, new Map(), () => -10);
    expect(total).toBe(0);
  });

  it("hands the estimator the STRIP page number, not the source's numbering", () => {
    // Anything filed per page — the reader's remembered page shapes — has to be
    // indexed the way the strip keys its rows, or a source that numbers pages
    // from 0 (or from a volume offset) reads back another page's height.
    const seen: number[] = [];
    freezeChapterHeight(one, new Map(), (_page, pageNumber) => {
      seen.push(pageNumber);
      return 1500;
    });
    expect(seen).toEqual([1, 2, 3]);
  });

  it("has nothing to freeze for a chapter with no pages", () => {
    const empty = { ...one, pages: [], pageCount: 0 };
    expect(freezeChapterHeight(empty, measured, estimate)).toEqual({
      total: 0,
      frozen: [],
    });
  });
});

describe("shouldPersistFrozenHeights", () => {
  it("remembers a chapter the reader has actually seen", () => {
    // Its rows carry real measurements; releasing and expanding must be
    // height-neutral, which is only true if those numbers are kept.
    expect(shouldPersistFrozenHeights(5, 3, true)).toBe(true);
  });

  it("forgets a never-seen chapter ahead of the reader", () => {
    // Read-all fetches six chapters a window and renders two either side, so
    // the far end is released without ever having been on screen. Every height
    // for it is the running average of other chapters — a guess that would
    // otherwise be honoured as a measurement when the reader arrives.
    expect(shouldPersistFrozenHeights(5, 2, false)).toBe(false);
  });

  it("still remembers a never-seen chapter BEHIND the reader", () => {
    // A multi-chapter prepend can leave one there, and it expands above the
    // reading line, where a change in total height moves the page under them.
    expect(shouldPersistFrozenHeights(0, 3, false)).toBe(true);
  });

  it("treats the reader's own chapter as ahead", () => {
    expect(shouldPersistFrozenHeights(3, 3, false)).toBe(false);
  });
});

describe("nextChapterLabelFor", () => {
  const numbered = { ...one, chapterNumber: 41, nextChapterKey: "ch-42", previousChapterKey: "ch-40" };

  it("names the neighbour from this chapter's own number", () => {
    expect(nextChapterLabelFor(numbered)).toBe("Ch 42");
    expect(nextChapterLabelFor(numbered, "previous")).toBe("Ch 40");
  });

  it("refuses to guess across a split chapter", () => {
    // 41.5's neighbour is not 42.5, and a wrong number is worse than none.
    const split = { ...numbered, chapterNumber: 41.5 };
    expect(nextChapterLabelFor(split)).toBe("Next chapter");
    expect(nextChapterLabelFor(split, "previous")).toBe("Previous chapter");
  });

  it("says nothing when there is no neighbour", () => {
    expect(nextChapterLabelFor({ ...numbered, nextChapterKey: null })).toBeNull();
    expect(
      nextChapterLabelFor({ ...numbered, previousChapterKey: null }, "previous"),
    ).toBeNull();
  });

  it("falls back for an unnumbered chapter", () => {
    expect(nextChapterLabelFor({ ...numbered, chapterNumber: null })).toBe("Next chapter");
  });
});
