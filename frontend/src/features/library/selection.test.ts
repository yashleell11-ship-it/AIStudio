import { describe, expect, it } from "vitest";
import {
  EMPTY_SELECTION,
  clearSelection,
  extendSelection,
  isSelected,
  orderedSelection,
  retainSelection,
  selectAll,
  selectionCount,
  selectionRange,
  toggleSelection,
} from "./selection";

const GRID = [10, 20, 30, 40, 50];

function selectionOf(ids: number[], anchor: number | null) {
  return { ids: new Set(ids), anchor };
}

function selected(state: { ids: ReadonlySet<number> }): number[] {
  return [...state.ids].sort((a, b) => a - b);
}

describe("selectionRange", () => {
  it("includes both endpoints", () => {
    expect(selectionRange(GRID, 20, 40)).toEqual([20, 30, 40]);
  });

  it("returns the same set when dragged upwards", () => {
    expect(selectionRange(GRID, 40, 20)).toEqual([20, 30, 40]);
  });

  it("returns a single id when both ends are the same card", () => {
    expect(selectionRange(GRID, 30, 30)).toEqual([30]);
  });

  it("returns nothing when an endpoint is not on screen", () => {
    // The anchor was filtered away between the two clicks.
    expect(selectionRange(GRID, 99, 40)).toEqual([]);
    expect(selectionRange(GRID, 20, 99)).toEqual([]);
  });
});

describe("toggleSelection", () => {
  it("selects an unselected id and anchors on it", () => {
    const next = toggleSelection(EMPTY_SELECTION, 30);
    expect(selected(next)).toEqual([30]);
    expect(next.anchor).toBe(30);
  });

  it("deselects a selected id but still anchors on it", () => {
    // Shift-clicking after "not that one" should measure from the card just
    // clicked, not from wherever the anchor happened to be before.
    const next = toggleSelection(selectionOf([30], 10), 30);
    expect(selected(next)).toEqual([]);
    expect(next.anchor).toBe(30);
  });

  it("leaves the previous state untouched", () => {
    const before = selectionOf([10], 10);
    toggleSelection(before, 20);
    expect(selected(before)).toEqual([10]);
  });
});

describe("extendSelection", () => {
  it("adds the anchor-to-target range", () => {
    const next = extendSelection(selectionOf([20], 20), 40, GRID);
    expect(selected(next)).toEqual([20, 30, 40]);
  });

  it("keeps the anchor so successive shift-clicks re-measure from it", () => {
    const first = extendSelection(selectionOf([20], 20), 40, GRID);
    const second = extendSelection(first, 50, GRID);
    expect(second.anchor).toBe(20);
    expect(selected(second)).toEqual([20, 30, 40, 50]);
  });

  it("does not drop a selection made elsewhere in the grid", () => {
    const next = extendSelection(selectionOf([10, 30], 30), 50, GRID);
    expect(selected(next)).toEqual([10, 30, 40, 50]);
  });

  it("works backwards", () => {
    const next = extendSelection(selectionOf([40], 40), 20, GRID);
    expect(selected(next)).toEqual([20, 30, 40]);
  });

  it("falls back to a plain click when there is no anchor yet", () => {
    const next = extendSelection(EMPTY_SELECTION, 30, GRID);
    expect(selected(next)).toEqual([30]);
    expect(next.anchor).toBe(30);
  });

  it("falls back to a plain click when the anchor is no longer visible", () => {
    // A filter changed under the user between the two clicks; a shift-click
    // that silently did nothing would read as a broken grid.
    const next = extendSelection(selectionOf([99], 99), 30, GRID);
    expect(selected(next)).toEqual([99, 30].sort((a, b) => a - b));
    expect(next.anchor).toBe(30);
  });
});

describe("selectAll", () => {
  it("takes every visible id and anchors on the first", () => {
    const next = selectAll(GRID);
    expect(selected(next)).toEqual(GRID);
    expect(next.anchor).toBe(10);
  });

  it("survives an empty grid", () => {
    expect(selectAll([])).toEqual({ ids: new Set(), anchor: null });
  });
});

describe("retainSelection", () => {
  it("drops ids that are no longer on screen", () => {
    const next = retainSelection(selectionOf([10, 99], 10), GRID);
    expect(selected(next)).toEqual([10]);
  });

  it("clears an anchor that was filtered away", () => {
    expect(retainSelection(selectionOf([10], 99), GRID).anchor).toBeNull();
  });

  it("returns the same object when nothing changed, so React can skip", () => {
    const before = selectionOf([10, 20], 10);
    expect(retainSelection(before, GRID)).toBe(before);
  });

  it("empties the selection when the grid does", () => {
    expect(selectionCount(retainSelection(selectionOf([10, 20], 10), []))).toBe(0);
  });
});

describe("orderedSelection", () => {
  it("returns the selected ids in display order", () => {
    expect(orderedSelection(selectionOf([50, 10, 30], 10), GRID)).toEqual([10, 30, 50]);
  });

  it("ignores ids that are not on screen", () => {
    expect(orderedSelection(selectionOf([30, 99], 30), GRID)).toEqual([30]);
  });
});

describe("isSelected / clearSelection", () => {
  it("reports membership", () => {
    expect(isSelected(selectionOf([10], null), 10)).toBe(true);
    expect(isSelected(selectionOf([10], null), 20)).toBe(false);
  });

  it("clears to nothing", () => {
    expect(selectionCount(clearSelection())).toBe(0);
    expect(clearSelection().anchor).toBeNull();
  });
});
