import { describe, expect, it } from "vitest";
import {
  clampZoom,
  continuousPageSizing,
  effectiveFitMode,
  MAX_ZOOM,
  MIN_ZOOM,
  pageAspect,
  resolvePageFit,
  wheelZoomSteps,
  zoomBy,
} from "./fit";

describe("clampZoom", () => {
  it("keeps zoom inside the supported range", () => {
    expect(clampZoom(0.1)).toBe(MIN_ZOOM);
    expect(clampZoom(99)).toBe(MAX_ZOOM);
    expect(clampZoom(1.234)).toBe(1.23);
  });

  it("falls back to 1 for junk values", () => {
    expect(clampZoom(Number.NaN)).toBe(1);
    expect(clampZoom(Number.POSITIVE_INFINITY)).toBe(1);
  });
});

describe("zoomBy", () => {
  it("steps in whole notches and clamps at the ends", () => {
    expect(zoomBy(1, 1)).toBeCloseTo(1.1);
    expect(zoomBy(1, -1)).toBeCloseTo(0.9);
    expect(zoomBy(MIN_ZOOM, -5)).toBe(MIN_ZOOM);
    expect(zoomBy(MAX_ZOOM, 5)).toBe(MAX_ZOOM);
  });
});

describe("wheelZoomSteps", () => {
  it("leaves a plain wheel to the scroller", () => {
    expect(wheelZoomSteps({ deltaY: -120, ctrlKey: false, metaKey: false })).toBe(0);
    expect(wheelZoomSteps({ deltaY: 120, ctrlKey: false, metaKey: false })).toBe(0);
  });

  it("zooms on ctrl or cmd wheel", () => {
    expect(wheelZoomSteps({ deltaY: -120, ctrlKey: true, metaKey: false })).toBe(1);
    expect(wheelZoomSteps({ deltaY: 120, ctrlKey: true, metaKey: false })).toBe(-1);
    expect(wheelZoomSteps({ deltaY: -1, ctrlKey: false, metaKey: true })).toBe(1);
  });

  it("ignores a wheel event that carries no movement", () => {
    expect(wheelZoomSteps({ deltaY: 0, ctrlKey: true, metaKey: false })).toBe(0);
    expect(wheelZoomSteps({ deltaY: Number.NaN, ctrlKey: true, metaKey: false })).toBe(0);
  });
});

describe("pageAspect", () => {
  it("uses real dimensions and falls back to 2/3", () => {
    expect(pageAspect(900, 1350)).toBeCloseTo(2 / 3);
    expect(pageAspect(null, null)).toBeCloseTo(2 / 3);
    expect(pageAspect(0, 1350)).toBeCloseTo(2 / 3);
  });
});

describe("effectiveFitMode", () => {
  it("degrades fit-height to fit-width while scrolling continuously", () => {
    expect(effectiveFitMode("height", "continuous")).toBe("width");
    expect(effectiveFitMode("original", "continuous")).toBe("width");
  });

  it("passes the chosen fit through in paged modes", () => {
    expect(effectiveFitMode("height", "single")).toBe("height");
    expect(effectiveFitMode("original", "double")).toBe("original");
  });
});

describe("resolvePageFit", () => {
  const base = {
    containerWidth: 1200,
    containerHeight: 800,
    pageWidth: 800,
    pageHeight: 1200,
    zoom: 1,
  };

  it("fills the container width and derives height from the aspect", () => {
    const fit = resolvePageFit({ ...base, fitMode: "width" });
    expect(fit.width).toBeCloseTo(1200);
    expect(fit.height).toBeCloseTo(1800);
  });

  it("fills the container height and derives width from the aspect", () => {
    const fit = resolvePageFit({ ...base, fitMode: "height" });
    expect(fit.height).toBeCloseTo(800);
    expect(fit.width).toBeCloseTo(800 * (800 / 1200));
  });

  it("renders original size at the page's intrinsic width", () => {
    const fit = resolvePageFit({ ...base, fitMode: "original" });
    expect(fit.width).toBeCloseTo(800);
    expect(fit.height).toBeCloseTo(1200);
  });

  it("splits the container between the two halves of a spread", () => {
    const fit = resolvePageFit({ ...base, fitMode: "width", slots: 2, gap: 16 });
    expect(fit.width).toBeCloseTo((1200 - 16) / 2);
  });

  it("multiplies the fitted box by the zoom level", () => {
    const fit = resolvePageFit({ ...base, fitMode: "width", zoom: 2 });
    expect(fit.width).toBeCloseTo(2400);
    expect(fit.height).toBeCloseTo(3600);
  });

  it("falls back to the container width when a page has no intrinsic size", () => {
    const fit = resolvePageFit({
      ...base,
      pageWidth: null,
      pageHeight: null,
      fitMode: "original",
    });
    expect(fit.width).toBeCloseTo(1200);
    expect(fit.height).toBeCloseTo(1200 / (2 / 3));
  });

  it("never returns a negative box for an unmeasured container", () => {
    const fit = resolvePageFit({
      containerWidth: 0,
      containerHeight: 0,
      fitMode: "width",
      zoom: 1,
      slots: 2,
      gap: 16,
    });
    expect(fit.width).toBe(0);
    expect(fit.height).toBe(0);
  });
});

describe("continuousPageSizing", () => {
  it("keeps the long strip capped at the reading column until zoomed in", () => {
    expect(continuousPageSizing(1)).toEqual({ width: "100%", maxWidth: "48rem" });
    expect(continuousPageSizing(0.8)).toEqual({ width: "80%", maxWidth: "48rem" });
  });

  it("lets the strip grow past the column once zoomed past 100%", () => {
    expect(continuousPageSizing(1.5)).toEqual({ width: "150%", maxWidth: "none" });
  });
});
