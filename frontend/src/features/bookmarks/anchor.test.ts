import { describe, expect, it } from "vitest";
import {
  anchorPositionFraction,
  anchorQuery,
  bookmarkAnchor,
  bookmarkChapterLabel,
  bookmarkMediaType,
  bookmarkPositionLabel,
  bookmarkSeriesLabel,
  clampFraction,
  fractionWithin,
  parseAnchorParams,
  pointWithin,
  resolveAnchor,
  withAnchorQuery,
} from "./anchor";
import type { Bookmark } from "./types";

function bookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 2,
    client_id: "dev-uuid-2",
    source_id: "mangadex",
    series_key: "tbate",
    series_title: null,
    chapter_key: "c14",
    chapter_number: 14,
    media_type: "manga",
    anchor_index: 7,
    anchor_fraction: 0.62,
    anchor_total: 11,
    page: 7,
    position_fraction: 0.6018,
    snippet: null,
    anchor_stale: false,
    note: null,
    deleted: false,
    created_at: "2026-09-05T10:00:00",
    updated_at: "2026-09-05T10:00:00",
    deleted_at: null,
    ...overrides,
  };
}

describe("clampFraction", () => {
  it("holds a fraction inside 0..1", () => {
    expect(clampFraction(0.62)).toBe(0.62);
    expect(clampFraction(-3)).toBe(0);
    expect(clampFraction(4)).toBe(1);
  });

  it("reads absent and unparseable values as zero rather than NaN", () => {
    expect(clampFraction(null)).toBe(0);
    expect(clampFraction(undefined)).toBe(0);
    expect(clampFraction(Number.NaN)).toBe(0);
    expect(clampFraction(Number.POSITIVE_INFINITY)).toBe(0);
  });
});

describe("bookmarkMediaType", () => {
  it("passes the two known media through", () => {
    expect(bookmarkMediaType("manga")).toBe("manga");
    expect(bookmarkMediaType("novel")).toBe("novel");
  });

  it("defaults anything else to manga rather than trusting the wire", () => {
    expect(bookmarkMediaType("audiobook")).toBe("manga");
    expect(bookmarkMediaType(null)).toBe("manga");
  });
});

describe("bookmarkAnchor", () => {
  it("reads the stored triple", () => {
    expect(bookmarkAnchor(bookmark())).toEqual({
      mediaType: "manga",
      index: 7,
      fraction: 0.62,
      total: 11,
    });
  });

  it("survives a migrated page-only row: index kept, nothing else claimed", () => {
    const anchor = bookmarkAnchor(
      bookmark({ anchor_index: 4, anchor_fraction: 0, anchor_total: 0 }),
    );
    expect(anchor).toEqual({ mediaType: "manga", index: 4, fraction: 0, total: 0 });
  });
});

describe("anchorPositionFraction", () => {
  it("matches the server's own rounding for the same anchor", () => {
    // bookmark_service.position_fraction((7 - 1 + 0.62) / 11) = 0.6018…
    expect(
      anchorPositionFraction({ mediaType: "manga", index: 7, fraction: 0.62, total: 11 }),
    ).toBe(0.6018);
  });

  it("is null, not zero, when the unit count is unknown", () => {
    expect(
      anchorPositionFraction({ mediaType: "manga", index: 4, fraction: 0, total: 0 }),
    ).toBeNull();
  });

  it("clamps an index past the end instead of reporting over 100%", () => {
    expect(
      anchorPositionFraction({ mediaType: "novel", index: 90, fraction: 1, total: 10 }),
    ).toBe(1);
  });
});

describe("resolveAnchor — degrade honestly", () => {
  it("leaves an in-range anchor alone and does not call it stale", () => {
    expect(resolveAnchor({ index: 7, fraction: 0.62 }, 11)).toEqual({
      index: 7,
      fraction: 0.62,
      stale: false,
    });
  });

  it("lands on the end of the last unit when the chapter shrank", () => {
    expect(resolveAnchor({ index: 400, fraction: 0.5 }, 300)).toEqual({
      index: 300,
      fraction: 1,
      stale: true,
    });
  });

  it("lands on the start of the first unit for an index below one", () => {
    expect(resolveAnchor({ index: 0, fraction: 0.5 }, 300)).toEqual({
      index: 1,
      fraction: 0,
      stale: true,
    });
  });

  it("is not stale merely because the chapter has not been measured yet", () => {
    expect(resolveAnchor({ index: 400, fraction: 0.5 }, 0)).toEqual({
      index: 400,
      fraction: 0.5,
      stale: false,
    });
  });

  it("takes the last unit exactly, not one past it", () => {
    expect(resolveAnchor({ index: 11, fraction: 0.3 }, 11).stale).toBe(false);
    expect(resolveAnchor({ index: 12, fraction: 0.3 }, 11).stale).toBe(true);
  });
});

describe("fractionWithin / pointWithin", () => {
  it("round-trips a point through its unit", () => {
    const fraction = fractionWithin(1420, 1200, 1600);
    expect(fraction).toBeCloseTo(0.55, 10);
    expect(pointWithin(fraction, 1200, 1600)).toBeCloseTo(1420, 6);
  });

  it("clamps a point outside its unit to the unit's ends", () => {
    expect(fractionWithin(900, 1200, 1600)).toBe(0);
    expect(fractionWithin(9000, 1200, 1600)).toBe(1);
  });

  it("resolves a not-yet-measured unit to its own start rather than NaN", () => {
    expect(fractionWithin(1200, 1200, 1200)).toBe(0);
    expect(pointWithin(0.5, 1200, 1200)).toBe(1200);
  });
});

describe("the URL round trip", () => {
  it("carries a manga anchor as page + at", () => {
    expect(
      anchorQuery({ mediaType: "manga", index: 7, fraction: 0.62, total: 11 }),
    ).toEqual({ page: "7", at: "0.62" });
  });

  it("carries a novel anchor as para + at, never page", () => {
    const query = anchorQuery({
      mediaType: "novel",
      index: 118,
      fraction: 0.25,
      total: 400,
    });
    expect(query).toEqual({ para: "118", at: "0.25" });
    expect(query.page).toBeUndefined();
  });

  it("appends to a chapter href that already carries a query", () => {
    const href = withAnchorQuery("/read-all/src/series?from=c14", {
      mediaType: "manga",
      index: 7,
      fraction: 0.62,
      total: 11,
    });
    const url = new URL(href, "https://example.test");
    expect(url.pathname).toBe("/read-all/src/series");
    expect(url.searchParams.get("from")).toBe("c14");
    expect(url.searchParams.get("page")).toBe("7");
    expect(url.searchParams.get("at")).toBe("0.62");
  });

  it("reads an anchor back off the route", () => {
    expect(parseAnchorParams("118", "0.25")).toEqual({ index: 118, fraction: 0.25 });
  });

  it("treats a plain chapter link as carrying no anchor at all", () => {
    expect(parseAnchorParams(undefined, undefined)).toBeNull();
    expect(parseAnchorParams("0", "0.5")).toBeNull();
    expect(parseAnchorParams("not-a-number", "0.5")).toBeNull();
  });

  it("keeps the index when only the fraction is missing or junk", () => {
    expect(parseAnchorParams("7", undefined)).toEqual({ index: 7, fraction: 0 });
    expect(parseAnchorParams("7", "wat")).toEqual({ index: 7, fraction: 0 });
  });
});

describe("labels", () => {
  it("names a numbered chapter and falls back to the opaque key", () => {
    expect(bookmarkChapterLabel(bookmark())).toBe("Chapter 14");
    expect(bookmarkChapterLabel(bookmark({ chapter_number: 14.5 }))).toBe("Chapter 14.5");
    expect(
      bookmarkChapterLabel(bookmark({ chapter_number: null, chapter_key: "vol-2/c14" })),
    ).toBe("vol-2/c14");
  });

  it("prints a percentage when the chapter's size was recorded", () => {
    expect(bookmarkPositionLabel(bookmark())).toBe("60% in");
  });

  it("names the unit instead of inventing a percentage", () => {
    expect(
      bookmarkPositionLabel(bookmark({ position_fraction: null, anchor_index: 4 })),
    ).toBe("Page 4");
    expect(
      bookmarkPositionLabel(
        bookmark({ position_fraction: null, anchor_index: 118, media_type: "novel" }),
      ),
    ).toBe("Paragraph 118");
  });

  it("prefers the series title and falls back to its key", () => {
    expect(bookmarkSeriesLabel(bookmark({ series_title: "TBATE" }))).toBe("TBATE");
    expect(bookmarkSeriesLabel(bookmark({ series_title: "  " }))).toBe("tbate");
    expect(bookmarkSeriesLabel(bookmark())).toBe("tbate");
  });
});
