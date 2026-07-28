import { describe, expect, it } from "vitest";
import {
  contrastBetween,
  contrastRatio,
  over,
  parseColor,
  relativeLuminance,
} from "./contrast";

describe("parseColor", () => {
  it("parses the hex forms the palette uses", () => {
    expect(parseColor("#000000")).toEqual({ r: 0, g: 0, b: 0, a: 1 });
    expect(parseColor("#FFFFFF")).toEqual({ r: 255, g: 255, b: 255, a: 1 });
    expect(parseColor("#9AA8B4")).toEqual({ r: 154, g: 168, b: 180, a: 1 });
    expect(parseColor("#fff")).toEqual({ r: 255, g: 255, b: 255, a: 1 });
  });

  it("parses hex with alpha", () => {
    const parsed = parseColor("#00000080");
    expect(parsed?.r).toBe(0);
    expect(parsed?.a).toBeCloseTo(0.502, 2);
  });

  it("parses rgb() and rgba()", () => {
    expect(parseColor("rgb(10, 20, 30)")).toEqual({ r: 10, g: 20, b: 30, a: 1 });
    expect(parseColor("rgba(221, 228, 234, 0.12)")).toEqual({
      r: 221,
      g: 228,
      b: 234,
      a: 0.12,
    });
  });

  it("returns null rather than guessing", () => {
    expect(parseColor("linear-gradient(180deg, #000, #fff)")).toBeNull();
    expect(parseColor("transparent")).toBeNull();
    expect(parseColor("")).toBeNull();
  });
});

describe("relativeLuminance", () => {
  it("anchors at black and white", () => {
    expect(relativeLuminance({ r: 0, g: 0, b: 0, a: 1 })).toBeCloseTo(0, 5);
    expect(relativeLuminance({ r: 255, g: 255, b: 255, a: 1 })).toBeCloseTo(1, 5);
  });
});

describe("contrastRatio", () => {
  it("gives 21:1 for black on white", () => {
    expect(contrastBetween("#000000", "#FFFFFF")).toBeCloseTo(21, 1);
  });

  it("gives 1:1 for a colour against itself", () => {
    expect(contrastBetween("#123456", "#123456")).toBeCloseTo(1, 5);
  });

  it("is symmetric", () => {
    expect(contrastBetween("#9AA8B4", "#0A0A0A")).toBeCloseTo(
      contrastBetween("#0A0A0A", "#9AA8B4"),
      5,
    );
  });

  it("matches the published value for a known pair", () => {
    // #767676 on white is the canonical "exactly AA" grey.
    expect(contrastBetween("#767676", "#FFFFFF")).toBeCloseTo(4.54, 1);
  });

  it("flattens a translucent foreground before scoring it", () => {
    // Scoring the raw colour would report the opaque ratio and pass text that
    // is barely visible on screen.
    const raw = contrastBetween("#9AA8B4", "#0A0A0A");
    const faded = contrastRatio(
      { r: 154, g: 168, b: 180, a: 0.4 },
      { r: 10, g: 10, b: 10, a: 1 },
    );
    expect(faded).toBeLessThan(raw);
    expect(faded).toBeLessThan(3);
  });
});

describe("over", () => {
  it("returns the foreground when fully opaque", () => {
    expect(over({ r: 1, g: 2, b: 3, a: 1 }, { r: 9, g: 9, b: 9, a: 1 })).toEqual({
      r: 1,
      g: 2,
      b: 3,
      a: 1,
    });
  });

  it("blends proportionally", () => {
    expect(
      over({ r: 0, g: 0, b: 0, a: 0.5 }, { r: 200, g: 100, b: 50, a: 1 }),
    ).toEqual({ r: 100, g: 50, b: 25, a: 1 });
  });
});
