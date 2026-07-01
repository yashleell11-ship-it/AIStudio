import type { KeyCombo } from "./types";

const isMac =
  typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform);

interface ParsedCombo {
  key: string;
  mod: boolean;
  ctrl: boolean;
  meta: boolean;
  alt: boolean;
  shift: boolean;
}

/** Parse a single combo segment (no chords) into its modifier flags + key. */
export function parseCombo(combo: KeyCombo): ParsedCombo {
  const normalized = combo.trim().toLowerCase();
  if (normalized === "+") {
    return {
      key: "=",
      mod: false,
      ctrl: false,
      meta: false,
      alt: false,
      shift: true,
    };
  }

  const parts = normalized.split("+").map((p) => p.trim());
  const parsed: ParsedCombo = {
    key: "",
    mod: false,
    ctrl: false,
    meta: false,
    alt: false,
    shift: false,
  };
  for (const part of parts) {
    switch (part) {
      case "mod":
        parsed.mod = true;
        break;
      case "ctrl":
      case "control":
        parsed.ctrl = true;
        break;
      case "cmd":
      case "meta":
        parsed.meta = true;
        break;
      case "alt":
      case "option":
        parsed.alt = true;
        break;
      case "shift":
        parsed.shift = true;
        break;
      default:
        parsed.key = part;
    }
  }
  return parsed;
}

/** Normalize an event key to the token used in combos. */
export function eventKey(event: KeyboardEvent): string {
  const key = event.key.toLowerCase();
  if (key === " ") return "space";
  return key;
}

/** Does a keydown event satisfy a single (non-chord) combo? */
export function matchesCombo(event: KeyboardEvent, combo: KeyCombo): boolean {
  const p = parseCombo(combo);
  const key = eventKey(event);
  const normalizedKey = key === "+" ? "=" : key;

  if (normalizedKey !== p.key) return false;

  // Shift+= reports key "+" and must not satisfy an unshifted "=" binding.
  if (key === "+" && !p.shift && combo.trim().toLowerCase() !== "+") {
    return false;
  }

  const wantCtrl = p.ctrl || (p.mod && !isMac);
  const wantMeta = p.meta || (p.mod && isMac);
  const wantShift = p.shift || combo.trim().toLowerCase() === "+";

  return (
    event.ctrlKey === wantCtrl &&
    event.metaKey === wantMeta &&
    event.altKey === p.alt &&
    event.shiftKey === wantShift
  );
}

/** True when focus is in a field where typing should usually win. */
export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}
