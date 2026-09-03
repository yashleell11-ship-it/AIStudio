import type { KeyCombo } from "./types";

/**
 * Combos that open the app-wide shortcuts cheat-sheet.
 *
 * "?" arrives as a shifted keypress on most layouts, and the matcher compares
 * the shift flag, so an unmodified "?" binding alone would never fire. The bare
 * form is kept for layouts where "?" is unshifted.
 *
 * Lives here rather than in the reader's keymap because the sheet is no longer
 * a reader overlay: the shell owns the binding and the sheet lists every
 * registered shortcut, reader bindings included.
 */
export const HELP_SHORTCUT_KEYS: KeyCombo[] = ["shift+?", "?"];
