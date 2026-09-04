import { describe, expect, it } from "vitest";
import {
  MAX_SHELF_GENRES,
  formatStatus,
  shelfBlurb,
  shelfGenres,
  shelfMetaParts,
  type ShelfBook,
} from "./shelf";

function book(overrides: Partial<ShelfBook> = {}): ShelfBook {
  return {
    key: "royalroad:1",
    href: "/sources/royalroad/series/1",
    title: "The Long Road",
    author: "A. Writer",
    description: null,
    chapterCount: 412,
    status: "ongoing",
    genres: [],
    coverUrl: null,
    note: null,
    ...overrides,
  };
}

describe("shelfMetaParts", () => {
  it("reads as one line of the facts a novel is recognised by", () => {
    expect(shelfMetaParts(book())).toEqual([
      "by A. Writer",
      "412 chapters",
      "Ongoing",
    ]);
  });

  it("drops what the source did not say, rather than rendering stray separators", () => {
    expect(
      shelfMetaParts(book({ author: null, chapterCount: 0, status: "  " })),
    ).toEqual([]);
    expect(shelfMetaParts(book({ author: null, status: null }))).toEqual([
      "412 chapters",
    ]);
  });

  it("carries a shelf-specific note last", () => {
    expect(shelfMetaParts(book({ note: "Reading · 42%" })).at(-1)).toBe(
      "Reading · 42%",
    );
    expect(shelfMetaParts(book({ note: "   " })).at(-1)).toBe("Ongoing");
  });
});

describe("formatStatus", () => {
  it("capitalises, because a lowercase word beside a byline reads as a typo", () => {
    expect(formatStatus("ongoing")).toBe("Ongoing");
    expect(formatStatus("Completed")).toBe("Completed");
    expect(formatStatus("  hiatus ")).toBe("Hiatus");
  });

  it("says nothing when there is no status", () => {
    expect(formatStatus(null)).toBeNull();
    expect(formatStatus(undefined)).toBeNull();
    expect(formatStatus("")).toBeNull();
    expect(formatStatus("   ")).toBeNull();
  });
});

describe("shelfGenres", () => {
  it("caps the list — aggregators tag twenty genres to a book", () => {
    const many = Array.from({ length: 25 }, (_, index) => `Genre ${index}`);
    expect(shelfGenres(many)).toHaveLength(MAX_SHELF_GENRES);
    expect(shelfGenres(many, 3)).toEqual(["Genre 0", "Genre 1", "Genre 2"]);
  });

  it("de-duplicates case-insensitively and drops blanks", () => {
    expect(shelfGenres(["Fantasy", "fantasy", " ", "LitRPG", "  Fantasy "])).toEqual([
      "Fantasy",
      "LitRPG",
    ]);
  });

  it("handles no genres at all", () => {
    expect(shelfGenres(null)).toEqual([]);
    expect(shelfGenres(undefined)).toEqual([]);
    expect(shelfGenres([])).toEqual([]);
  });
});

describe("shelfBlurb", () => {
  it("collapses the whitespace connectors leave in, so a clamp clamps text", () => {
    expect(shelfBlurb("  A man   wakes\n\nup.\t Again. ")).toBe(
      "A man wakes up. Again.",
    );
  });

  it("treats a whitespace-only description as no description", () => {
    expect(shelfBlurb(null)).toBeNull();
    expect(shelfBlurb(undefined)).toBeNull();
    expect(shelfBlurb("   \n  ")).toBeNull();
  });
});
