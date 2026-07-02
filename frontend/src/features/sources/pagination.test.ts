import { describe, expect, it } from "vitest";
import { dedupeSeriesItems } from "./pagination";
import type { SourceSeriesSummary } from "./types";

function series(id: string, title: string): SourceSeriesSummary {
  return {
    id,
    source_id: "asurascans",
    title,
    chapter_count: 1,
    description: null,
    author: null,
    artist: null,
    status: null,
    genres: [],
    latest_chapter: null,
    cover_url: `/cover/${id}`,
  };
}

describe("dedupeSeriesItems", () => {
  it("removes duplicate series ids while preserving order", () => {
    const items = [
      series("a", "Alpha"),
      series("b", "Beta"),
      series("a", "Alpha duplicate"),
      series("c", "Gamma"),
    ];
    const result = dedupeSeriesItems(items);
    expect(result.map((item) => item.id)).toEqual(["a", "b", "c"]);
    expect(result[0]?.title).toBe("Alpha");
  });

  it("returns empty array for empty input", () => {
    expect(dedupeSeriesItems([])).toEqual([]);
  });
});
