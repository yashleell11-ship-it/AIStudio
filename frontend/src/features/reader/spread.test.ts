import { describe, expect, it } from "vitest";
import {
  buildPageViews,
  buildSpreads,
  clampViewIndex,
  findViewIndex,
  spreadDisplayOrder,
  viewLeadPage,
} from "./spread";

describe("buildSpreads", () => {
  it("stands the cover alone so the drawn spreads stay in phase", () => {
    expect(buildSpreads(6)).toEqual([[1], [2, 3], [4, 5], [6]]);
    expect(buildSpreads(5)).toEqual([[1], [2, 3], [4, 5]]);
  });

  it("pairs from page one when the chapter has no cover", () => {
    expect(buildSpreads(5, false)).toEqual([
      [1, 2],
      [3, 4],
      [5],
    ]);
  });

  it("handles the degenerate chapter lengths", () => {
    expect(buildSpreads(0)).toEqual([]);
    expect(buildSpreads(-3)).toEqual([]);
    expect(buildSpreads(Number.NaN)).toEqual([]);
    expect(buildSpreads(1)).toEqual([[1]]);
    expect(buildSpreads(2)).toEqual([[1], [2]]);
  });
});

describe("buildPageViews", () => {
  it("gives one page per view outside double-page mode", () => {
    expect(buildPageViews(3, "single")).toEqual([[1], [2], [3]]);
    expect(buildPageViews(3, "continuous")).toEqual([[1], [2], [3]]);
  });

  it("pairs into spreads in double-page mode", () => {
    expect(buildPageViews(4, "double")).toEqual([[1], [2, 3], [4]]);
  });
});

describe("spreadDisplayOrder", () => {
  it("puts the earlier page on the right when reading right-to-left", () => {
    expect(spreadDisplayOrder([2, 3], "rtl")).toEqual([3, 2]);
    expect(spreadDisplayOrder([2, 3], "ltr")).toEqual([2, 3]);
  });

  it("leaves a lone cover alone in both directions", () => {
    expect(spreadDisplayOrder([1], "rtl")).toEqual([1]);
    expect(spreadDisplayOrder([1], "ltr")).toEqual([1]);
  });

  it("does not mutate the view it was given", () => {
    const view = [2, 3];
    spreadDisplayOrder(view, "rtl");
    expect(view).toEqual([2, 3]);
  });
});

describe("findViewIndex", () => {
  const views = buildSpreads(6);

  it("finds the spread holding a page", () => {
    expect(findViewIndex(views, 1)).toBe(0);
    expect(findViewIndex(views, 3)).toBe(1);
    expect(findViewIndex(views, 6)).toBe(3);
  });

  it("clamps pages outside the chapter to the nearest end", () => {
    expect(findViewIndex(views, 0)).toBe(0);
    expect(findViewIndex(views, 99)).toBe(3);
    expect(findViewIndex([], 4)).toBe(0);
  });
});

describe("viewLeadPage", () => {
  it("reports the first page read in the view", () => {
    expect(viewLeadPage([2, 3])).toBe(2);
    expect(viewLeadPage([3, 2])).toBe(2);
    expect(viewLeadPage([])).toBe(1);
  });
});

describe("clampViewIndex", () => {
  it("makes paging past either end a no-op", () => {
    const views = buildSpreads(6);
    expect(clampViewIndex(views, -1)).toBe(0);
    expect(clampViewIndex(views, 99)).toBe(3);
    expect(clampViewIndex([], 5)).toBe(0);
  });
});
