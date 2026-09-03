import { describe, expect, it } from "vitest";
import { ocrResultHref } from "./result-link";
import type { OcrSearchResultItem } from "./types";

function hit(overrides: Partial<OcrSearchResultItem> = {}): OcrSearchResultItem {
  return {
    source_id: "asura",
    series_key: "nano-machine",
    chapter_key: "ch-210",
    word_count: 120,
    engine: "tesseract",
    snippet: "the <mark>hero</mark> speaks",
    highlighted_terms: ["hero"],
    ...overrides,
  };
}

describe("ocrResultHref", () => {
  it("maps a hit to the source-native reader route", () => {
    expect(ocrResultHref(hit())).toBe("/reader/asura/nano-machine/ch-210");
  });

  it("encodes opaque keys that contain slashes as path segments", () => {
    expect(
      ocrResultHref(hit({ series_key: "a/b", chapter_key: "vol/1/ch/2" })),
    ).toBe("/reader/asura/a%2Fb/vol/1/ch/2");
  });

  it("does not append a page query (search has no page offset)", () => {
    expect(ocrResultHref(hit()).includes("?")).toBe(false);
  });
});
