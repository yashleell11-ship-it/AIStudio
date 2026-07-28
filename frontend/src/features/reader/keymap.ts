import type { ReadingDirection } from "./types";

/**
 * Combos that open the shortcuts overlay.
 *
 * "?" arrives as a shifted keypress on most layouts, and the matcher compares
 * the shift flag, so an unmodified "?" binding alone would never fire. The bare
 * form is kept for layouts where "?" is unshifted.
 */
export const HELP_SHORTCUT_KEYS = ["shift+?", "?"];

/**
 * Combo that leaves the chapter for its own series page.
 *
 * "S" for series, unmodified like every other reader binding, and free of the
 * keys already bound (A/D, H/J/K/L, B, F, 0/-/=). Deliberately NOT ⌘/Ctrl+S:
 * the registry calls `preventDefault` on a match, so a modified binding here
 * would swallow the browser's own Save.
 */
export const SERIES_SHORTCUT_KEYS = "s";

/** What a page-turn input resolves to once reading direction is applied. */
export type PageTurn = "advance" | "retreat";

/**
 * Arrow keys, A/D and edge taps name a direction of travel, not a command. In a
 * right-to-left chapter the next page lives to the LEFT, so the pair swaps.
 * J/K, Space and the chapter keys are logical, never mirrored.
 */
export function horizontalTurn(
  side: "left" | "right",
  direction: ReadingDirection,
): PageTurn {
  const forwardSide = direction === "rtl" ? "left" : "right";
  return side === forwardSide ? "advance" : "retreat";
}

/** Label for the shortcut registry, which flips with the direction it describes. */
export function horizontalTurnDescription(
  side: "left" | "right",
  direction: ReadingDirection,
): string {
  return horizontalTurn(side, direction) === "advance" ? "Next page" : "Previous page";
}

export type EscapeTarget = "help" | "fullscreen" | "reader";

/**
 * Escape peels one layer at a time — the shortcuts overlay, then fullscreen,
 * then the reader itself — so it never drops the user two levels at once.
 */
export function resolveEscapeTarget(state: {
  helpOpen: boolean;
  fullscreen: boolean;
}): EscapeTarget {
  if (state.helpOpen) return "help";
  if (state.fullscreen) return "fullscreen";
  return "reader";
}

export type TapZone = PageTurn | "toggle";

/**
 * Touch and mouse equivalent of the arrow keys: the outer bands of the page turn,
 * the middle toggles the chrome. Mirrored for right-to-left exactly like the keys.
 */
export function tapZone(
  clientX: number,
  rect: { left: number; width: number },
  direction: ReadingDirection,
  edgeRatio = 0.28,
): TapZone {
  if (!(rect.width > 0)) return "toggle";

  const ratio = (clientX - rect.left) / rect.width;
  if (!Number.isFinite(ratio) || ratio < 0 || ratio > 1) return "toggle";

  const edge = Math.min(0.5, Math.max(0, edgeRatio));
  if (ratio <= edge) return horizontalTurn("left", direction);
  if (ratio >= 1 - edge) return horizontalTurn("right", direction);
  return "toggle";
}
