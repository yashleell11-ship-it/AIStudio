import { describe, expect, it } from "vitest";
import {
  DEFAULT_SHORTCUT_GROUP,
  groupShortcuts,
  shortcutCombos,
} from "./groups";
import type { Shortcut } from "./types";

function shortcut(
  id: string,
  description: string,
  group?: string,
  keys: string | string[] = "x",
): Shortcut {
  return { id, description, group, keys, handler: () => {} };
}

describe("groupShortcuts", () => {
  it("orders known groups by the canonical order, not registration order", () => {
    const groups = groupShortcuts([
      shortcut("r", "Turn page", "Reader"),
      shortcut("l", "Focus library search", "Library"),
      shortcut("g", "Open the command palette", "General"),
    ]);

    expect(groups.map((group) => group.name)).toEqual([
      "General",
      "Library",
      "Reader",
    ]);
  });

  it("files an ungrouped shortcut under the default group", () => {
    const groups = groupShortcuts([shortcut("a", "Do a thing")]);

    expect(groups).toHaveLength(1);
    expect(groups[0].name).toBe(DEFAULT_SHORTCUT_GROUP);
  });

  it("sorts unknown groups alphabetically after the known ones", () => {
    const groups = groupShortcuts([
      shortcut("z", "Zeta", "Zeta"),
      shortcut("d", "Downloads thing", "Downloads"),
      shortcut("r", "Turn page", "Reader"),
    ]);

    expect(groups.map((group) => group.name)).toEqual([
      "Reader",
      "Downloads",
      "Zeta",
    ]);
  });

  it("sorts shortcuts inside a group by description", () => {
    const groups = groupShortcuts([
      shortcut("b", "Zoom in", "Reader"),
      shortcut("a", "Bookmark this page", "Reader"),
    ]);

    expect(groups[0].shortcuts.map((item) => item.description)).toEqual([
      "Bookmark this page",
      "Zoom in",
    ]);
  });

  it("omits groups that have no shortcuts registered right now", () => {
    const groups = groupShortcuts([shortcut("g", "Toggle the sidebar", "General")]);

    expect(groups.map((group) => group.name)).toEqual(["General"]);
  });

  it("returns nothing for an empty registry", () => {
    expect(groupShortcuts([])).toEqual([]);
  });
});

describe("shortcutCombos", () => {
  it("normalises a single combo to an array", () => {
    expect(shortcutCombos(shortcut("a", "A", "General", "mod+k"))).toEqual(["mod+k"]);
  });

  it("passes an array of combos through", () => {
    expect(
      shortcutCombos(shortcut("a", "A", "General", ["arrowright", "d"])),
    ).toEqual(["arrowright", "d"]);
  });
});
