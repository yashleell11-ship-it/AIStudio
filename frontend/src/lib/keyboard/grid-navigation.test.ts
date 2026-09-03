import { describe, expect, it } from "vitest";
import {
  gridMoveForKey,
  isGridVimKey,
  measureGridColumns,
  nextGridIndex,
} from "./grid-navigation";

describe("gridMoveForKey", () => {
  it("maps the arrow keys", () => {
    expect(gridMoveForKey("ArrowLeft")).toBe("prev");
    expect(gridMoveForKey("ArrowRight")).toBe("next");
    expect(gridMoveForKey("ArrowUp")).toBe("up");
    expect(gridMoveForKey("ArrowDown")).toBe("down");
  });

  it("maps the vim keys to the same moves", () => {
    expect(gridMoveForKey("h")).toBe("prev");
    expect(gridMoveForKey("l")).toBe("next");
    expect(gridMoveForKey("k")).toBe("up");
    expect(gridMoveForKey("j")).toBe("down");
  });

  it("maps Home and End to the ends of the grid", () => {
    expect(gridMoveForKey("Home")).toBe("first");
    expect(gridMoveForKey("End")).toBe("last");
  });

  it("ignores keys that are not movement", () => {
    expect(gridMoveForKey("Enter")).toBeNull();
    expect(gridMoveForKey("/")).toBeNull();
    expect(gridMoveForKey("f")).toBeNull();
  });

  it("knows which keys the registry owns", () => {
    expect(isGridVimKey("J")).toBe(true);
    expect(isGridVimKey("ArrowDown")).toBe(false);
  });
});

describe("nextGridIndex", () => {
  const grid = { count: 11, columns: 4 };

  it("walks the flat list left and right, wrapping around row edges", () => {
    expect(nextGridIndex("next", { ...grid, index: 3 })).toBe(4);
    expect(nextGridIndex("prev", { ...grid, index: 4 })).toBe(3);
  });

  it("refuses to move past either end of the list", () => {
    expect(nextGridIndex("prev", { ...grid, index: 0 })).toBeNull();
    expect(nextGridIndex("next", { ...grid, index: 10 })).toBeNull();
  });

  it("moves a whole row vertically", () => {
    expect(nextGridIndex("down", { ...grid, index: 1 })).toBe(5);
    expect(nextGridIndex("up", { ...grid, index: 5 })).toBe(1);
  });

  it("refuses to move above the first row", () => {
    expect(nextGridIndex("up", { ...grid, index: 2 })).toBeNull();
  });

  it("lands on the last item when the final row is short", () => {
    // 11 items over 4 columns: the last row holds 8, 9, 10 only.
    expect(nextGridIndex("down", { ...grid, index: 7 })).toBe(10);
  });

  it("refuses to move down from the last row", () => {
    expect(nextGridIndex("down", { ...grid, index: 9 })).toBeNull();
    expect(nextGridIndex("down", { ...grid, index: 10 })).toBeNull();
  });

  it("treats a single-column layout as a plain list", () => {
    expect(nextGridIndex("down", { count: 3, columns: 1, index: 0 })).toBe(1);
    expect(nextGridIndex("up", { count: 3, columns: 1, index: 2 })).toBe(1);
    expect(nextGridIndex("down", { count: 3, columns: 1, index: 2 })).toBeNull();
  });

  it("jumps to either end of the grid", () => {
    expect(nextGridIndex("first", { ...grid, index: 7 })).toBe(0);
    expect(nextGridIndex("last", { ...grid, index: 7 })).toBe(10);
    expect(nextGridIndex("first", { ...grid, index: 0 })).toBeNull();
    expect(nextGridIndex("last", { ...grid, index: 10 })).toBeNull();
  });

  it("returns null for an empty grid or an out-of-range index", () => {
    expect(nextGridIndex("next", { count: 0, columns: 4, index: 0 })).toBeNull();
    expect(nextGridIndex("next", { count: 4, columns: 4, index: 9 })).toBeNull();
    expect(nextGridIndex("next", { count: 4, columns: 4, index: -1 })).toBeNull();
  });

  it("survives a nonsense column count rather than dividing by zero", () => {
    expect(nextGridIndex("down", { count: 3, columns: 0, index: 0 })).toBe(1);
  });
});

describe("measureGridColumns", () => {
  it("counts the items sharing the first row's top edge", () => {
    expect(measureGridColumns([0, 0, 0, 0, 200, 200, 200, 200])).toBe(4);
  });

  it("handles a single row", () => {
    expect(measureGridColumns([12, 12, 12])).toBe(3);
  });

  it("handles a single column", () => {
    expect(measureGridColumns([0, 80, 160])).toBe(1);
  });

  it("never reports zero columns", () => {
    expect(measureGridColumns([])).toBe(1);
  });
});
