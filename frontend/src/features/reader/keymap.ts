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

/**
 * Combo that toggles cinema mode (auto-hiding of all reader chrome).
 *
 * "C" for cinema, unmodified like every other reader binding and clear of the
 * keys already bound (A/D, H/J/K/L, B, F, S, 0/-/=).
 */
export const CINEMA_SHORTCUT_KEYS = "c";

/**
 * Combo that plays/pauses auto-scroll (continuous mode only — a no-op
 * elsewhere).
 *
 * "P" for play/pause, unmodified like every other reader binding. Free
 * app-wide (the command palette and sidebar toggle use mod+ combos, search
 * uses "/") and clear of every other reader binding (A/D, H/J/K/L, B, C, F,
 * S, 0/-/=). Deliberately not Space: Space already advances one screen in the
 * reader, and repurposing it would make the most-pressed key in the whole
 * keymap ambiguous between "scroll" and "toggle auto-scroll".
 */
export const AUTO_SCROLL_SHORTCUT_KEYS = "p";

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

/** The three horizontal bands a tap can land in, before any action is applied. */
export type TapZonePosition = "left" | "center" | "right";

/** Purely geometric: which band `clientX` falls in. Independent of direction —
 * only the ACTION a band performs is direction-aware, never the band itself. */
function tapZonePosition(
  clientX: number,
  rect: { left: number; width: number },
  edgeRatio: number,
): TapZonePosition {
  if (!(rect.width > 0)) return "center";

  const ratio = (clientX - rect.left) / rect.width;
  if (!Number.isFinite(ratio) || ratio < 0 || ratio > 1) return "center";

  const edge = Math.min(0.5, Math.max(0, edgeRatio));
  if (ratio <= edge) return "left";
  if (ratio >= 1 - edge) return "right";
  return "center";
}

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
  return resolveTapZone(clientX, rect, defaultTapZoneConfig(direction), edgeRatio);
}

/**
 * Configurable tap-zone behaviour (reader settings §3 "tap-zone customisation").
 * Each physical band gets an explicit action: `TapZone` is reused verbatim
 * (`"advance" | "retreat" | "toggle"`) rather than inventing a parallel
 * "previous/next" vocabulary, because `"advance"`/`"retreat"` already name the
 * page-number direction independent of reading direction — exactly what a
 * configured zone should mean regardless of which series it's applied to.
 */
export interface TapZoneConfig {
  left: TapZone;
  center: TapZone;
  right: TapZone;
}

/**
 * The zone behaviour before any customisation — reproduces exactly what
 * `tapZone` has always done: the outer bands turn the page (mirrored for a
 * right-to-left chapter via {@link horizontalTurn}), the middle toggles the
 * chrome. Used both as `tapZone`'s own implementation and as the default a
 * settings UI seeds itself from.
 */
export function defaultTapZoneConfig(direction: ReadingDirection): TapZoneConfig {
  return {
    left: horizontalTurn("left", direction),
    center: "toggle",
    right: horizontalTurn("right", direction),
  };
}

/**
 * The continuous strip's legacy behaviour: a tap anywhere toggles the chrome,
 * because there is no single "page" to turn to under a thumb — the whole
 * column is one continuous image. This is the strip's default until a reader
 * opts into edge-tap page jumping via the same {@link TapZoneConfig}.
 */
export const TOGGLE_ONLY_TAP_ZONES: TapZoneConfig = {
  left: "toggle",
  center: "toggle",
  right: "toggle",
};

/**
 * Resolve a tap against an explicit zone configuration. Pass
 * {@link defaultTapZoneConfig} or {@link TOGGLE_ONLY_TAP_ZONES} for the
 * legacy behaviour of the paged and continuous views respectively; a reader
 * who has customised their tap zones passes their stored config instead.
 * `config` is required (not nullable) — resolving "no customisation yet" to a
 * concrete default is the caller's job, since paged and continuous views
 * disagree about what that default is.
 */
export function resolveTapZone(
  clientX: number,
  rect: { left: number; width: number },
  config: TapZoneConfig,
  edgeRatio = 0.28,
): TapZone {
  return config[tapZonePosition(clientX, rect, edgeRatio)];
}
