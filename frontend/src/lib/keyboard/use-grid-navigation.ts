"use client";

import { useCallback, useRef, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { useShortcut } from "./context";
import {
  GRID_VIM_KEYS,
  gridMoveForKey,
  isGridVimKey,
  measureGridColumns,
  nextGridIndex,
  type GridMove,
} from "./grid-navigation";
import { isEditableTarget } from "./match";

/** Marks a focusable cell. Set by the card components, read by this hook. */
export const GRID_ITEM_ATTRIBUTE = "data-grid-item";
const ITEM_SELECTOR = `[${GRID_ITEM_ATTRIBUTE}]`;

export interface GridNavigationOptions {
  /** Registry id for the vim-key binding; unique per mounted grid. */
  id: string;
  /** Cheat-sheet group, e.g. "Library" or "Sources". */
  group: string;
  /** Cheat-sheet wording, e.g. "Move through the series grid". */
  description: string;
  /** False while the grid shows skeletons or an empty state. */
  enabled?: boolean;
}

export interface GridNavigationProps {
  ref: (node: HTMLElement | null) => void;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
}

/**
 * Arrow-key (and H/J/K/L) movement across a grid of cards.
 *
 * Deliberately NOT a roving-tabindex implementation: every card stays in the
 * tab order, so nothing about existing Tab behaviour changes and the cards need
 * no extra props beyond the `data-grid-item` marker. This only adds a faster
 * way to move once you are in the grid — and a way in, since the vim keys are
 * registered app-wide for the grid's lifetime and focus the first card when
 * nothing in the grid has focus yet.
 *
 * A move that cannot happen (Up from the first row, Down from the last) is left
 * to the browser, so the arrow keys still scroll the page at the edges instead
 * of feeling stuck.
 */
export function useGridNavigation({
  id,
  group,
  description,
  enabled = true,
}: GridNavigationOptions): GridNavigationProps {
  const containerRef = useRef<HTMLElement | null>(null);

  const setContainer = useCallback((node: HTMLElement | null) => {
    containerRef.current = node;
  }, []);

  const move = useCallback((requested: GridMove): boolean => {
    const container = containerRef.current;
    if (!container) return false;

    const items = Array.from(container.querySelectorAll<HTMLElement>(ITEM_SELECTOR));
    if (items.length === 0) return false;

    const active = document.activeElement;
    const index = items.findIndex(
      (item) => item === active || (active instanceof Node && item.contains(active)),
    );

    // Not in the grid yet: the first press is the way in, whichever key it was.
    const target =
      index === -1
        ? 0
        : nextGridIndex(requested, {
            index,
            count: items.length,
            columns: measureGridColumns(items.map((item) => item.offsetTop)),
          });
    if (target === null) return false;

    // `preventScroll` then `scrollIntoView`: focus's own scrolling centres the
    // card, which yanks the grid around on every keypress.
    items[target].focus({ preventScroll: true });
    items[target].scrollIntoView({ block: "nearest", inline: "nearest" });
    return true;
  }, []);

  // Arrow keys and Home/End, from inside the grid only — binding those globally
  // would take the page's own scrolling away from anyone not using the grid.
  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLElement>) => {
      if (!enabled) return;
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      if (isEditableTarget(event.target)) return;
      // The registry already handles these; letting both run would move twice.
      if (isGridVimKey(event.key)) return;
      const requested = gridMoveForKey(event.key);
      if (!requested) return;
      if (move(requested)) event.preventDefault();
    },
    [enabled, move],
  );

  useShortcut({
    id: `${id}.navigate`,
    keys: [...GRID_VIM_KEYS],
    description,
    group,
    enabled,
    handler: useCallback(
      (event: KeyboardEvent) => {
        const requested = gridMoveForKey(event.key);
        if (requested) move(requested);
      },
      [move],
    ),
  });

  return { ref: setContainer, onKeyDown };
}
