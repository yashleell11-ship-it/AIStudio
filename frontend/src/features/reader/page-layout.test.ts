import { describe, expect, it } from "vitest";
import {
  estimatePageHeight,
  exactPageHeight,
  pageAspectRatio,
  pageContainerStyle,
  UNKNOWN_PAGE_ASPECT,
} from "./page-layout";
import type { ReaderPage } from "./types";

function makePage(width: number | null, height: number | null): ReaderPage {
  return {
    id: "chapter:1",
    number: 1,
    width,
    height,
    imageUrl: "/sources/asurascans/pages/chapter%3A1/image",
  };
}

describe("pageAspectRatio", () => {
  it("uses real dimensions when available", () => {
    expect(pageAspectRatio(900, 16000)).toBe("900 / 16000");
  });

  it("falls back to the measured population prior when dimensions are unknown", () => {
    const fallback = `1 / ${UNKNOWN_PAGE_ASPECT}`;
    expect(pageAspectRatio(null, null)).toBe(fallback);
    expect(pageAspectRatio(undefined, undefined)).toBe(fallback);
    expect(pageAspectRatio(0, 100)).toBe(fallback);
  });

  it("uses the SAME prior the height estimate does", () => {
    // The placeholder box is what the row measures as before the image
    // decodes. If the two priors disagreed, every first paint would hand the
    // virtualizer a measurement contradicting its own estimate.
    const [w, h] = pageAspectRatio(null, null).split(" / ").map(Number);
    expect(estimatePageHeight(makePage(null, null), 768, 1)).toBeCloseTo((768 / w) * h);
  });
});

describe("pageContainerStyle", () => {
  it("reserves placeholder space while the image is loading", () => {
    expect(pageContainerStyle(false, null, null)).toEqual({
      aspectRatio: `1 / ${UNKNOWN_PAGE_ASPECT}`,
    });
    expect(pageContainerStyle(false, 900, 16000)).toEqual({
      aspectRatio: "900 / 16000",
    });
  });

  it("never constrains a loaded image (regression: AsuraScans tall pages were clipped to 2/3)", () => {
    // Sources like AsuraScans provide no page dimensions and serve strips up to
    // 900x16000. A loaded page must always lay out at its intrinsic height;
    // any returned constraint here would clip page content invisibly.
    expect(pageContainerStyle(true, null, null)).toBeUndefined();
    expect(pageContainerStyle(true, undefined, undefined)).toBeUndefined();
    expect(pageContainerStyle(true, 900, 16000)).toBeUndefined();
    expect(pageContainerStyle(true, 800, 1200)).toBeUndefined();
  });
});

describe("estimatePageHeight", () => {
  it("scales known dimensions to the content width", () => {
    const page = makePage(900, 16000);
    expect(estimatePageHeight(page, 768, 1)).toBeCloseTo((768 / 900) * 16000);
  });

  it("uses the measured fallback only when dimensions are unknown", () => {
    const page = makePage(null, null);
    expect(estimatePageHeight(page, 768, 1)).toBeCloseTo(768 * UNKNOWN_PAGE_ASPECT);
  });

  it("reserves a real webtoon strip's extent instead of guessing 13x short", () => {
    // The case this exists for: 900x16000 in a 768px column lays out at
    // ~13,653px. The old fixed-aspect guess reserved 1,152px for it.
    const strip = makePage(900, 16000);
    const reserved = estimatePageHeight(strip, 768, 1);
    expect(reserved).toBeCloseTo(13653.33, 1);
    expect(reserved / (768 * 1.5)).toBeGreaterThan(11);
  });

  it("scales with zoom, so a zoomed strip still reserves its own height", () => {
    const strip = makePage(900, 16000);
    expect(estimatePageHeight(strip, 768, 2)).toBeCloseTo(
      estimatePageHeight(strip, 768, 1) * 2,
    );
  });

  it("clamps to the reader column, not the whole viewport", () => {
    const strip = makePage(900, 16000);
    expect(estimatePageHeight(strip, 1920, 1)).toBeCloseTo(
      estimatePageHeight(strip, 768, 1),
    );
  });
});

describe("exactPageHeight", () => {
  it("answers only for pages the source actually measured", () => {
    expect(exactPageHeight(makePage(900, 16000), 768, 1)).toBeCloseTo(13653.33, 1);
    expect(exactPageHeight(makePage(null, null), 768, 1)).toBeNull();
    expect(exactPageHeight(makePage(900, null), 768, 1)).toBeNull();
    expect(exactPageHeight(makePage(0, 1200), 768, 1)).toBeNull();
    expect(exactPageHeight(makePage(800, 0), 768, 1)).toBeNull();
  });
});
