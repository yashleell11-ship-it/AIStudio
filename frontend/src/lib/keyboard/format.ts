import { parseCombo } from "./match";
import type { KeyCombo } from "./types";

const isMac =
  typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform);

function formatKeyToken(key: string): string {
  if (key === "=" || key === "+") {
    return "+";
  }
  if (key === "space") {
    return "Space";
  }
  if (key.length === 1) {
    return key.toUpperCase();
  }
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/** Human-readable tokens for a single key combo (e.g. ["Ctrl", "B"]). */
export function formatKeyCombo(combo: KeyCombo): string[] {
  const parsed = parseCombo(combo);
  const tokens: string[] = [];

  if (parsed.mod) {
    tokens.push(isMac ? "⌘" : "Ctrl");
  } else {
    if (parsed.ctrl) tokens.push("Ctrl");
    if (parsed.meta) tokens.push(isMac ? "⌘" : "Meta");
  }
  if (parsed.alt) tokens.push(isMac ? "⌥" : "Alt");
  if (parsed.shift) tokens.push("⇧");
  tokens.push(formatKeyToken(parsed.key));

  return tokens;
}
