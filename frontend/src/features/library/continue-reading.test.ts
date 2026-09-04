import { describe, expect, it } from "vitest";
import {
  continueReadingChapterLabel,
  continueReadingKey,
  continueReadingPercent,
  continueReadingRef,
  resolveSeriesTitle,
} from "./continue-reading";
import type { ContinueReadingItem } from "./types";

const item: ContinueReadingItem = {
  source_id: "asura",
  series_key: "series/nano-machine",
  chapter_key: "ch/210",
  chapter_number: 210,
  last_page: 7,
  page_count: 24,
  last_read_at: "2026-09-03T10:00:00Z",
};

describe("continue-reading source-native identity", () => {
  it("keys and refs every item by (source_id, series_key, chapter_key)", () => {
    expect(continueReadingRef(item)).toEqual({
      sourceId: "asura",
      seriesKey: "series/nano-machine",
      chapterKey: "ch/210",
    });
    expect(continueReadingKey(item)).toBe("asura:series/nano-machine:ch/210");
  });

  it("joins the series title from the followed index, falling back to the key", () => {
    const titles = new Map([["asura:series/nano-machine", "Nano Machine"]]);
    expect(resolveSeriesTitle(item, titles)).toBe("Nano Machine");
    expect(resolveSeriesTitle(item, new Map())).toBe("series/nano-machine");
  });

  it("computes a clamped chapter-progress percentage", () => {
    expect(continueReadingPercent(item)).toBe(29);
    expect(continueReadingPercent({ ...item, page_count: 0 })).toBe(0);
    expect(continueReadingPercent({ ...item, last_page: 999 })).toBe(100);
  });

  it("labels the chapter by number, or the raw key when there is none", () => {
    expect(continueReadingChapterLabel(item)).toBe("Ch 210");
    expect(continueReadingChapterLabel({ ...item, chapter_number: null })).toBe("ch/210");
  });
});
