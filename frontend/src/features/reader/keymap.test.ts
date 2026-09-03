import { describe, expect, it } from "vitest";
import { matchesCombo } from "@/lib/keyboard/match";
import {
  AUTO_SCROLL_SHORTCUT_KEYS,
  HELP_SHORTCUT_KEYS,
  SERIES_SHORTCUT_KEYS,
  TOGGLE_ONLY_TAP_ZONES,
  defaultTapZoneConfig,
  horizontalTurn,
  horizontalTurnDescription,
  resolveEscapeTarget,
  resolveTapZone,
  tapZone,
  type TapZoneConfig,
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

  it("jumps to the series page on a bare S", () => {
    expect(matchesCombo(keyEvent("s"), SERIES_SHORTCUT_KEYS)).toBe(true);
    expect(matchesCombo(keyEvent("S", { shiftKey: true }), SERIES_SHORTCUT_KEYS)).toBe(
      false,
    );
  });

  it("leaves the browser's own Ctrl/⌘+S alone", () => {
    expect(matchesCombo(keyEvent("s", { ctrlKey: true }), SERIES_SHORTCUT_KEYS)).toBe(
      false,
    );
    expect(matchesCombo(keyEvent("s", { metaKey: true }), SERIES_SHORTCUT_KEYS)).toBe(
      false,
    );
  });

  it("does not collide with a key the reader already binds", () => {
    const bound = ["a", "d", "h", "j", "k", "l", "b", "f", "0", "-", "=", "?"];
    for (const key of bound) {
      expect(matchesCombo(keyEvent(key), SERIES_SHORTCUT_KEYS)).toBe(false);
    }
  });

  it("plays/pauses auto-scroll on a bare P, clear of every other binding", () => {
    expect(matchesCombo(keyEvent("p"), AUTO_SCROLL_SHORTCUT_KEYS)).toBe(true);
    const bound = ["a", "d", "h", "j", "k", "l", "b", "c", "f", "s", "0", "-", "=", "?"];
    for (const key of bound) {
      expect(matchesCombo(keyEvent(key), AUTO_SCROLL_SHORTCUT_KEYS)).toBe(false);
    }
    // And Space (the screen-advance key) is untouched by the new binding.
    expect(matchesCombo(keyEvent(" "), AUTO_SCROLL_SHORTCUT_KEYS)).toBe(false);
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

describe("defaultTapZoneConfig", () => {
  it("matches tapZone's own LTR behaviour", () => {
    expect(defaultTapZoneConfig("ltr")).toEqual({
      left: "retreat",
      center: "toggle",
      right: "advance",
    });
  });

  it("mirrors for RTL, matching tapZone's own RTL behaviour", () => {
    expect(defaultTapZoneConfig("rtl")).toEqual({
      left: "advance",
      center: "toggle",
      right: "retreat",
    });
  });
});

describe("TOGGLE_ONLY_TAP_ZONES", () => {
  it("is the continuous strip's legacy tap-anywhere-toggles behaviour", () => {
    expect(TOGGLE_ONLY_TAP_ZONES).toEqual({
      left: "toggle",
      center: "toggle",
      right: "toggle",
    });
  });
});

describe("resolveTapZone", () => {
  const rect = { left: 0, width: 1000 };

  it("reproduces tapZone exactly when given the direction-derived default", () => {
    for (const direction of ["ltr", "rtl"] as const) {
      const config = defaultTapZoneConfig(direction);
      for (const x of [50, 500, 950]) {
        expect(resolveTapZone(x, rect, config)).toBe(tapZone(x, rect, direction));
      }
    }
  });

  it("never turns a page under TOGGLE_ONLY_TAP_ZONES, regardless of tap position", () => {
    for (const x of [10, 250, 500, 750, 990]) {
      expect(resolveTapZone(x, rect, TOGGLE_ONLY_TAP_ZONES)).toBe("toggle");
    }
  });

  it("applies a fully custom mapping literally, by physical zone", () => {
    // A left-handed one-tap-forward layout: left always advances, right always
    // retreats, center still toggles — independent of reading direction.
    const custom: TapZoneConfig = { left: "advance", center: "toggle", right: "retreat" };
    expect(resolveTapZone(50, rect, custom)).toBe("advance");
    expect(resolveTapZone(500, rect, custom)).toBe("toggle");
    expect(resolveTapZone(950, rect, custom)).toBe("retreat");
  });

  it("falls back to the center (toggle) band on unusable geometry", () => {
    const config = defaultTapZoneConfig("ltr");
    expect(resolveTapZone(10, { left: 0, width: 0 }, config)).toBe("toggle");
    expect(resolveTapZone(-10, rect, config)).toBe("toggle");
    expect(resolveTapZone(2000, rect, config)).toBe("toggle");
  });
});
