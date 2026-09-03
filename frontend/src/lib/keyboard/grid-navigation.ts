/**
 * Keyboard movement across a wrapped grid of cards (the library shelf, a
 * source's catalog).
 *
 * Pure index maths, kept out of the hook so the awkward cases — the last row
 * being short, a single-column phone layout, an empty grid — are unit-testable
 * without a DOM. The hook (`use-grid-navigation.ts`) owns focus and measuring.
 */

export type GridMove = "prev" | "next" | "up" | "down" | "first" | "last";

/**
 * Vim-style movement keys. These are bound through the keyboard REGISTRY (so
 * they work before anything in the grid has focus, and show up in the `?`
 * sheet); the arrow keys are handled by the container's own keydown, which only
 * ever fires with focus already inside the grid. Splitting them that way is
 * what keeps a single press from being handled twice.
 */
export const GRID_VIM_KEYS = ["h", "j", "k", "l"] as const;

const KEY_MOVES: Record<string, GridMove> = {
  arrowleft: "prev",
  h: "prev",
  arrowright: "next",
  l: "next",
  arrowup: "up",
  k: "up",
  arrowdown: "down",
  j: "down",
  home: "first",
  end: "last",
};

/** The movement a key asks for, or null when the key is not ours. */
export function gridMoveForKey(key: string): GridMove | null {
  return KEY_MOVES[key.toLowerCase()] ?? null;
}

export function isGridVimKey(key: string): boolean {
  return (GRID_VIM_KEYS as readonly string[]).includes(key.toLowerCase());
}

export interface GridMoveInput {
  /** Currently focused item, 0-based. */
  index: number;
  count: number;
  /** Items per row, as measured from the laid-out DOM. */
  columns: number;
}

/**
 * Where a move lands, or `null` when it cannot move — the caller uses null to
 * decide NOT to swallow the keypress, so ArrowDown on the last row still
 * scrolls the page instead of dying silently.
 *
 * `prev`/`next` walk the flat list, so they wrap around a row edge (which is
 * what reading order means for a wrapped grid). `up`/`down` move a whole row
 * and refuse to leave the grid; `down` from the last full row lands on the last
 * item even when the final row is short, so the end of a catalog is always
 * reachable.
 */
export function nextGridIndex(move: GridMove, input: GridMoveInput): number | null {
  const { index, count } = input;
  const columns = Math.max(1, Math.floor(input.columns));
  if (count <= 0) return null;
  if (index < 0 || index >= count) return null;

  switch (move) {
    case "prev":
      return index > 0 ? index - 1 : null;
    case "next":
      return index < count - 1 ? index + 1 : null;
    case "up":
      return index - columns >= 0 ? index - columns : null;
    case "down": {
      const straightDown = index + columns;
      if (straightDown < count) return straightDown;
      // A short final row: land on its last item rather than refusing to move.
      const lastRow = Math.floor((count - 1) / columns);
      return Math.floor(index / columns) < lastRow ? count - 1 : null;
    }
    case "first":
      return index > 0 ? 0 : null;
    case "last":
      return index < count - 1 ? count - 1 : null;
  }
}

/**
 * Items per row, inferred from laid-out offsets: everything sharing the first
 * item's top edge is row one.
 *
 * Measured rather than derived from the Tailwind breakpoint classes, because
 * the grid's column count is decided by CSS at six breakpoints and by the
 * library's density setting — re-deriving that in JS would be a second source
 * of truth that silently rots.
 */
export function measureGridColumns(tops: readonly number[]): number {
  if (tops.length === 0) return 1;
  const first = tops[0];
  let columns = 0;
  for (const top of tops) {
    if (top !== first) break;
    columns += 1;
  }
  return Math.max(1, columns);
}
