import { describe, expect, it } from "vitest";
import {
  duplicateSurplusCount,
  findDuplicateSeries,
  normalizeSeriesTitle,
} from "./duplicates";
import type { SeriesSummary } from "./types";

function series(overrides: Partial<SeriesSummary> & { id: number; title: string }): SeriesSummary {
  return {
    library_id: 1,
    sort_title: overrides.title,
    original_title: null,
    author: null,
    artist: null,
    description: null,
    status: null,
    content_rating: "safe",
    language: "ko",
    year: null,
    cover_path: null,
    folder_path: "/library/x",
    is_favorite: false,
    reading_status: "unread",
    chapter_count: 0,
    read_chapters: 0,
    page_count: 0,
    total_chapters: 0,
    total_pages: 0,
    first_chapter_id: null,
    created_at: "2026-01-01T00:00:00",
    updated_at: "2026-01-01T00:00:00",
    reading_progress: null,
    ...overrides,
  };
}

describe("normalizeSeriesTitle", () => {
  it("collapses whitespace and casefolds, like the backend helper", () => {
    expect(normalizeSeriesTitle("  Solo   Leveling\n")).toBe("solo leveling");
    expect(normalizeSeriesTitle("SOLO LEVELING")).toBe("solo leveling");
  });

  it("does not strip punctuation, so distinct titles stay distinct", () => {
    // Mirrors _normalize_title exactly: it only touches whitespace and case.
    expect(normalizeSeriesTitle("Re:Zero")).toBe("re:zero");
    expect(normalizeSeriesTitle("Re Zero")).not.toBe(normalizeSeriesTitle("Re:Zero"));
  });
});

describe("findDuplicateSeries", () => {
  it("finds nothing in a library with unique titles", () => {
    expect(
      findDuplicateSeries([
        series({ id: 1, title: "Solo Leveling" }),
        series({ id: 2, title: "Tower of God" }),
      ]),
    ).toEqual([]);
  });

  it("groups the same title followed from two sources", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "Solo Leveling" }),
      series({ id: 2, title: "Tower of God" }),
      series({ id: 3, title: "solo   leveling" }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("solo leveling");
    expect(groups[0].series.map((item) => item.id)).toEqual([1, 3]);
  });

  it("puts the copy with the most read chapters first", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "Omniscient Reader", read_chapters: 0, chapter_count: 200 }),
      series({ id: 2, title: "Omniscient Reader", read_chapters: 40, chapter_count: 60 }),
    ]);

    expect(groups[0].series.map((item) => item.id)).toEqual([2, 1]);
  });

  it("falls back to the more complete copy when neither has been read", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "Eleceed", chapter_count: 12 }),
      series({ id: 2, title: "Eleceed", chapter_count: 250 }),
    ]);

    expect(groups[0].series.map((item) => item.id)).toEqual([2, 1]);
  });

  it("falls back to the one followed first when both are otherwise equal", () => {
    const groups = findDuplicateSeries([
      series({ id: 9, title: "Eleceed", created_at: "2026-05-02T00:00:00" }),
      series({ id: 4, title: "Eleceed", created_at: "2026-01-09T00:00:00" }),
    ]);

    expect(groups[0].series.map((item) => item.id)).toEqual([4, 9]);
  });

  it("keeps a triple together instead of splitting it into pairs", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "Nano Machine" }),
      series({ id: 2, title: "NANO MACHINE" }),
      series({ id: 3, title: "nano machine " }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].series).toHaveLength(3);
  });

  it("displays the ranked head's title as written", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "nano   machine", read_chapters: 1 }),
      series({ id: 2, title: "Nano Machine" }),
    ]);

    expect(groups[0].title).toBe("nano   machine");
  });

  it("skips blank titles rather than collapsing them into one group", () => {
    expect(
      findDuplicateSeries([
        series({ id: 1, title: "   " }),
        series({ id: 2, title: "" }),
      ]),
    ).toEqual([]);
  });

  it("reports groups in first-seen order, so a title-sorted list scans in order", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "Bastard" }),
      series({ id: 2, title: "Bastard" }),
      series({ id: 3, title: "Aquarium" }),
      series({ id: 4, title: "Aquarium" }),
    ]);

    expect(groups.map((group) => group.key)).toEqual(["bastard", "aquarium"]);
  });
});

describe("duplicateSurplusCount", () => {
  it("counts one fewer than each group holds", () => {
    const groups = findDuplicateSeries([
      series({ id: 1, title: "A" }),
      series({ id: 2, title: "A" }),
      series({ id: 3, title: "A" }),
      series({ id: 4, title: "B" }),
      series({ id: 5, title: "B" }),
    ]);

    expect(duplicateSurplusCount(groups)).toBe(3);
  });

  it("is zero for a clean library", () => {
    expect(duplicateSurplusCount([])).toBe(0);
  });
});
