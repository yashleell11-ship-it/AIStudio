import { describe, expect, it } from "vitest";
import { HELP_SHORTCUT_KEYS } from "./help";
import { matchesCombo } from "./match";

describe("HELP_SHORTCUT_KEYS", () => {
  it("matches a shifted '?' — the only way most layouts produce the character", () => {
    const event = { key: "?", shiftKey: true, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent;

    expect(HELP_SHORTCUT_KEYS.some((combo) => matchesCombo(event, combo))).toBe(true);
  });

  it("matches an unshifted '?' for layouts where it needs no modifier", () => {
    const event = { key: "?", shiftKey: false, ctrlKey: false, metaKey: false, altKey: false } as KeyboardEvent;

    expect(HELP_SHORTCUT_KEYS.some((combo) => matchesCombo(event, combo))).toBe(true);
  });
});
