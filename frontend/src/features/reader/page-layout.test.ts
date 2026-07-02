import { describe, expect, it } from "vitest";
import {
  estimatePageHeight,
  pageAspectRatio,
  pageContainerStyle,
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

  it("falls back to 2/3 when dimensions are unknown", () => {
    expect(pageAspectRatio(null, null)).toBe("2 / 3");
    expect(pageAspectRatio(undefined, undefined)).toBe("2 / 3");
    expect(pageAspectRatio(0, 100)).toBe("2 / 3");
  });
});

describe("pageContainerStyle", () => {
  it("reserves placeholder space while the image is loading", () => {
    expect(pageContainerStyle(false, null, null)).toEqual({ aspectRatio: "2 / 3" });
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

  it("uses the 3/2 fallback only when dimensions are unknown", () => {
    const page = makePage(null, null);
    expect(estimatePageHeight(page, 768, 1)).toBeCloseTo(768 * 1.5);
  });
});
