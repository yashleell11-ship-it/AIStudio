import { describe, expect, it } from "vitest";
import { seriesPageHref } from "./series-link";

describe("seriesPageHref", () => {
  it("points a local chapter at its library series page", () => {
    expect(seriesPageHref({ scope: "local", seriesId: 42 })).toBe("/library/42");
  });

  it("falls back to the library when the reader route carries no usable id", () => {
    expect(seriesPageHref({ scope: "local", seriesId: Number.NaN })).toBe("/library");
    expect(seriesPageHref({ scope: "local", seriesId: 0 })).toBe("/library");
    expect(seriesPageHref({ scope: "local", seriesId: -1 })).toBe("/library");
  });

  it("points a source chapter at that source's series page", () => {
    expect(
      seriesPageHref({ scope: "source", sourceId: "mangadex", seriesId: "abc123" }),
    ).toBe("/sources/mangadex/series/abc123");
  });

  it("percent-encodes a connector series id containing slashes", () => {
    expect(
      seriesPageHref({
        scope: "source",
        sourceId: "asura",
        seriesId: "manga/solo-leveling",
      }),
    ).toBe("/sources/asura/series/manga%2Fsolo-leveling");
  });

  it("percent-encodes the source id too, so a nested id cannot forge a segment", () => {
    expect(
      seriesPageHref({ scope: "source", sourceId: "a b/c", seriesId: "x?y" }),
    ).toBe("/sources/a%20b%2Fc/series/x%3Fy");
  });
});
