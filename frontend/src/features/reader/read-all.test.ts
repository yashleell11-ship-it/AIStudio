import { describe, expect, it } from "vitest";
import type { SourceChapterSummary } from "@/features/sources/types";
import {
  keyBefore,
  orderedLabel,
  orderIndexOf,
  readAllEntryKey,
  readingOrder,
  windowAfter,
  type OrderedChapter,
} from "./read-all";

function summary(
  id: string,
  number: number | null,
  title = `Chapter ${number}`,
): SourceChapterSummary {
  return {
    id,
    source_id: "asurascans",
    series_id: "series/one",
    title,
    number,
    page_count: 0,
    release_date: null,
  };
}

describe("readingOrder", () => {
  it("puts chapter one first however the source listed them", () => {
    const order = readingOrder([summary("c3", 3), summary("c1", 1), summary("c2", 2)]);
    expect(order.map((entry) => entry.chapterKey)).toEqual(["c1", "c2", "c3"]);
  });

  it("keeps decimal chapters in their real place", () => {
    const order = readingOrder([summary("c2", 2), summary("c15", 1.5), summary("c1", 1)]);
    expect(order.map((entry) => entry.chapterKey)).toEqual(["c1", "c15", "c2"]);
  });

  it("sinks unnumbered chapters to the end in source order", () => {
    const order = readingOrder([
      summary("extra", null, "Omake"),
      summary("c2", 2),
      summary("side", null, "Side story"),
      summary("c1", 1),
    ]);
    expect(order.map((entry) => entry.chapterKey)).toEqual([
      "c1",
      "c2",
      "extra",
      "side",
    ]);
  });

  it("is stable for chapters that share a number", () => {
    const order = readingOrder([summary("a", 7), summary("b", 7)]);
    expect(order.map((entry) => entry.chapterKey)).toEqual(["a", "b"]);
  });
});

describe("windowAfter", () => {
  const order: OrderedChapter[] = Array.from({ length: 10 }, (_, index) => ({
    chapterKey: `c${index + 1}`,
    number: index + 1,
    title: `Chapter ${index + 1}`,
  }));

  it("starts at the beginning when nothing is loaded yet", () => {
    expect(windowAfter(order, undefined, 1, 3, 20)).toEqual(["c1", "c2", "c3"]);
  });

  it("asks for a whole stride even when only one chapter is needed", () => {
    expect(windowAfter(order, "c2", 1, 4, 20)).toEqual(["c3", "c4", "c5", "c6"]);
  });

  it("asks for more than the stride when the strip needs more", () => {
    expect(windowAfter(order, "c1", 6, 4, 20)).toHaveLength(6);
  });

  it("never asks for more than the server's cap", () => {
    expect(windowAfter(order, "c1", 30, 30, 4)).toEqual(["c2", "c3", "c4", "c5"]);
  });

  it("runs out at the end of the series", () => {
    expect(windowAfter(order, "c9", 1, 5, 20)).toEqual(["c10"]);
    expect(windowAfter(order, "c10", 1, 5, 20)).toEqual([]);
  });

  it("answers nothing for a key the series does not have", () => {
    expect(windowAfter(order, "gone", 1, 5, 20)).toEqual([]);
    expect(windowAfter([], undefined, 1, 5, 20)).toEqual([]);
  });
});

describe("keyBefore", () => {
  const order: OrderedChapter[] = [
    { chapterKey: "c1", number: 1, title: "Chapter 1" },
    { chapterKey: "c2", number: 2, title: "Chapter 2" },
  ];

  it("steps back one chapter", () => {
    expect(keyBefore(order, "c2")).toBe("c1");
  });

  it("has nothing before the first chapter", () => {
    expect(keyBefore(order, "c1")).toBeNull();
    expect(keyBefore(order, undefined)).toBeNull();
    expect(keyBefore(order, "gone")).toBeNull();
  });
});

describe("orderedLabel", () => {
  const order: OrderedChapter[] = [
    { chapterKey: "c1", number: 1, title: "Chapter 1" },
    { chapterKey: "extra", number: null, title: "Omake" },
    { chapterKey: "blank", number: null, title: "   " },
  ];

  it("names a numbered chapter by its number", () => {
    expect(orderedLabel(order, "c1")).toBe("Ch 1");
  });

  it("falls back to the title, then to nothing", () => {
    expect(orderedLabel(order, "extra")).toBe("Omake");
    expect(orderedLabel(order, "blank")).toBeNull();
    expect(orderedLabel(order, "gone")).toBeNull();
    expect(orderedLabel(order, null)).toBeNull();
  });
});

describe("readAllEntryKey", () => {
  const order: OrderedChapter[] = [
    { chapterKey: "c1", number: 1, title: "Chapter 1" },
    { chapterKey: "c2", number: 2, title: "Chapter 2" },
  ];

  it("resumes where the reader got to", () => {
    expect(readAllEntryKey(order, "c2")).toBe("c2");
  });

  it("starts at chapter one with no progress, or progress the source lost", () => {
    expect(readAllEntryKey(order, null)).toBe("c1");
    expect(readAllEntryKey(order, "deleted")).toBe("c1");
  });

  it("has nowhere to start in an empty series", () => {
    expect(readAllEntryKey([], null)).toBeNull();
  });
});

describe("orderIndexOf", () => {
  it("locates a chapter, or -1", () => {
    const order: OrderedChapter[] = [{ chapterKey: "c1", number: 1, title: "one" }];
    expect(orderIndexOf(order, "c1")).toBe(0);
    expect(orderIndexOf(order, "c2")).toBe(-1);
  });
});
