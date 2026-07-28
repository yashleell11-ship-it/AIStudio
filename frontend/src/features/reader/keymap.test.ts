import { describe, expect, it } from "vitest";
import { matchesCombo } from "@/lib/keyboard/match";
import {
  HELP_SHORTCUT_KEYS,
  horizontalTurn,
  horizontalTurnDescription,
  resolveEscapeTarget,
  tapZone,
} from "./keymap";

function keyEvent(
  key: string,
  modifiers: Partial<Record<"shiftKey" | "ctrlKey" | "metaKey" | "altKey", boolean>> = {},
): KeyboardEvent {
  return {
    key,
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    ...modifiers,
  } as KeyboardEvent;
}

describe("reader key bindings", () => {
  it("opens the overlay on a shifted question mark", () => {
    const event = keyEvent("?", { shiftKey: true });
    expect(HELP_SHORTCUT_KEYS.some((combo) => matchesCombo(event, combo))).toBe(true);
  });

  it("keeps Space and Shift+Space distinct so the first match is the right one", () => {
    expect(matchesCombo(keyEvent(" "), "space")).toBe(true);
    expect(matchesCombo(keyEvent(" ", { shiftKey: true }), "space")).toBe(false);
    expect(matchesCombo(keyEvent(" ", { shiftKey: true }), "shift+space")).toBe(true);
  });

  it("binds the page keys the registry will actually receive", () => {
    expect(matchesCombo(keyEvent("ArrowLeft"), "arrowleft")).toBe(true);
    expect(matchesCombo(keyEvent("ArrowRight"), "arrowright")).toBe(true);
    expect(matchesCombo(keyEvent("Home"), "home")).toBe(true);
    expect(matchesCombo(keyEvent("End"), "end")).toBe(true);
    expect(matchesCombo(keyEvent("Escape"), "escape")).toBe(true);
  });
});

describe("horizontalTurn", () => {
  it("advances rightward in a left-to-right chapter", () => {
    expect(horizontalTurn("right", "ltr")).toBe("advance");
    expect(horizontalTurn("left", "ltr")).toBe("retreat");
  });

  it("advances leftward in a right-to-left chapter", () => {
    expect(horizontalTurn("left", "rtl")).toBe("advance");
    expect(horizontalTurn("right", "rtl")).toBe("retreat");
  });

  it("labels the key by what it does, not where it points", () => {
    expect(horizontalTurnDescription("left", "ltr")).toBe("Previous page");
    expect(horizontalTurnDescription("left", "rtl")).toBe("Next page");
  });
});

describe("resolveEscapeTarget", () => {
  it("closes the overlay before anything else", () => {
    expect(resolveEscapeTarget({ helpOpen: true, fullscreen: true })).toBe("help");
  });

  it("leaves fullscreen before leaving the reader", () => {
    expect(resolveEscapeTarget({ helpOpen: false, fullscreen: true })).toBe("fullscreen");
  });

  it("exits the reader when nothing is layered over it", () => {
    expect(resolveEscapeTarget({ helpOpen: false, fullscreen: false })).toBe("reader");
  });
});

describe("tapZone", () => {
  const rect = { left: 0, width: 1000 };

  it("turns the page from the edges and toggles from the middle", () => {
    expect(tapZone(50, rect, "ltr")).toBe("retreat");
    expect(tapZone(950, rect, "ltr")).toBe("advance");
    expect(tapZone(500, rect, "ltr")).toBe("toggle");
  });

  it("mirrors the edges for a right-to-left chapter", () => {
    expect(tapZone(50, rect, "rtl")).toBe("advance");
    expect(tapZone(950, rect, "rtl")).toBe("retreat");
  });

  it("accounts for the container offset", () => {
    expect(tapZone(450, { left: 200, width: 1000 }, "ltr")).toBe("retreat");
    expect(tapZone(450, { left: 0, width: 1000 }, "ltr")).toBe("toggle");
  });

  it("falls back to toggling when the geometry is unusable", () => {
    expect(tapZone(10, { left: 0, width: 0 }, "ltr")).toBe("toggle");
    expect(tapZone(-10, rect, "ltr")).toBe("toggle");
    expect(tapZone(2000, rect, "ltr")).toBe("toggle");
  });
});
