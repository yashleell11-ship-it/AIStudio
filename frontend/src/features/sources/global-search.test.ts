import { describe, expect, it } from "vitest";
import { globalSearchHref, globalSearchScopeLabel } from "./global-search";
import { prettifySourceId } from "./source-branding";
import type { GlobalSearchItem } from "./types";

function item(overrides: Partial<GlobalSearchItem> = {}): GlobalSearchItem {
  return {
    kind: "source",
    source: "mangadex",
    series_id: "abc-123",
    title: "Some Series",
    cover_url: "https://cdn.example.com/cover.jpg",
    author: null,
    extra: null,
    ...overrides,
  };
}

describe("globalSearchHref", () => {
  it("routes local hits to the library series route", () => {
    expect(globalSearchHref(item({ kind: "local", source: null, series_id: "42" }))).toBe(
      "/library/42",
    );
  });

  it("routes source hits to the source series route", () => {
    expect(globalSearchHref(item({ source: "mangadex", series_id: "abc-123" }))).toBe(
      "/sources/mangadex/series/abc-123",
    );
  });

  it("percent-encodes source series ids containing unsafe path characters", () => {
    expect(
      globalSearchHref(item({ source: "toonily", series_id: "manga/slug?x=1" })),
    ).toBe("/sources/toonily/series/manga%2Fslug%3Fx%3D1");
  });
});

describe("globalSearchScopeLabel", () => {
  it("returns null when no sources were queried", () => {
    expect(globalSearchScopeLabel(0, 0)).toBeNull();
  });

  it("summarizes the queried source count", () => {
    expect(globalSearchScopeLabel(5, 0)).toBe("Searched 5 sources");
  });

  it("uses the singular noun for a single source", () => {
    expect(globalSearchScopeLabel(1, 0)).toBe("Searched 1 source");
  });

  it("appends a failed count when some sources failed", () => {
    expect(globalSearchScopeLabel(5, 2)).toBe("Searched 5 sources (2 failed)");
  });
});

describe("prettifySourceId", () => {
  it("capitalizes a source id", () => {
    expect(prettifySourceId("mangadex")).toBe("Mangadex");
  });

  it("returns an empty string unchanged", () => {
    expect(prettifySourceId("")).toBe("");
  });
});
