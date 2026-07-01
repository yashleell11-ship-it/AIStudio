import { describe, expect, it } from "vitest";
import { matchesCombo, parseCombo } from "./match";

describe("parseCombo", () => {
  it("parses lone plus as shifted equals", () => {
    expect(parseCombo("+")).toEqual({
      key: "=",
      mod: false,
      ctrl: false,
      meta: false,
      alt: false,
      shift: true,
    });
  });
});

describe("matchesCombo", () => {
  it("matches shift+= for zoom in", () => {
    const event = {
      key: "+",
      ctrlKey: false,
      metaKey: false,
      altKey: false,
      shiftKey: true,
    } as KeyboardEvent;

    expect(matchesCombo(event, "=")).toBe(false);
    expect(matchesCombo(event, "+")).toBe(true);
    expect(matchesCombo(event, "shift+=")).toBe(true);
  });
});
