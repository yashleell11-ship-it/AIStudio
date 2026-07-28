import { describe, expect, it } from "vitest";
import {
  groupCommands,
  rankCommands,
  routeCommands,
  type Command,
} from "./commands";

const ROUTES: Command[] = routeCommands([
  { href: "/", label: "Home" },
  { href: "/library", label: "Library" },
  { href: "/downloads", label: "Downloads" },
  { href: "/settings", label: "Settings" },
]);

const ACTIONS: Command[] = [
  {
    id: "action:theme",
    title: "Toggle theme",
    group: "Actions",
    kind: "action",
    keywords: ["dark", "light", "sepia"],
  },
  { id: "action:signout", title: "Sign out", group: "Actions", kind: "action" },
];

const SERIES: Command[] = [
  {
    id: "series:1",
    title: "Solo Levelling",
    group: "Library",
    kind: "series",
    href: "/library/1",
  },
  {
    id: "series:2",
    title: "Tower of God",
    group: "Library",
    kind: "series",
    href: "/library/2",
  },
];

const ALL = [...SERIES, ...ROUTES, ...ACTIONS];

describe("routeCommands", () => {
  it("makes one command per route, keyed by href", () => {
    expect(ROUTES).toHaveLength(4);
    expect(ROUTES[1]).toMatchObject({
      id: "route:/library",
      title: "Library",
      href: "/library",
      kind: "route",
      group: "Go to",
    });
  });

  it("de-duplicates a destination listed in more than one nav group", () => {
    const commands = routeCommands([
      { href: "/settings", label: "Settings" },
      { href: "/settings", label: "More" },
    ]);
    expect(commands).toHaveLength(1);
    expect(commands[0].title).toBe("Settings");
  });
});

describe("rankCommands", () => {
  it("returns everything, in declaration order, for an empty query", () => {
    const ranked = rankCommands(ALL, "");
    expect(ranked).toHaveLength(ALL.length);
    // All scores tie at 0, so GROUP_ORDER decides: Library, Sources, Go to, Actions.
    expect(ranked.map((c) => c.group)).toEqual([
      "Library",
      "Library",
      "Go to",
      "Go to",
      "Go to",
      "Go to",
      "Actions",
      "Actions",
    ]);
  });

  it("drops commands the query cannot match", () => {
    const ranked = rankCommands(ALL, "zzzz");
    expect(ranked).toEqual([]);
  });

  it("puts the exact destination first", () => {
    expect(rankCommands(ALL, "downloads")[0].id).toBe("route:/downloads");
    expect(rankCommands(ALL, "sett")[0].id).toBe("route:/settings");
  });

  it("finds a series by a fragment of its title", () => {
    expect(rankCommands(ALL, "levell")[0].id).toBe("series:1");
    expect(rankCommands(ALL, "tower")[0].id).toBe("series:2");
  });

  it("finds an action by a keyword it does not display", () => {
    const ranked = rankCommands(ALL, "sepia");
    expect(ranked[0].id).toBe("action:theme");
  });

  it("respects the limit", () => {
    expect(rankCommands(ALL, "", 3)).toHaveLength(3);
  });

  it("is stable for equally-scored hits", () => {
    const first = rankCommands(ALL, "").map((c) => c.id);
    const second = rankCommands(ALL, "").map((c) => c.id);
    expect(first).toEqual(second);
  });

  it("carries the match indices through for highlighting", () => {
    const [top] = rankCommands(ALL, "down");
    expect(top.match.indices).toEqual([0, 1, 2, 3]);
  });
});

describe("groupCommands", () => {
  it("keeps ranked order and only emits groups that matched", () => {
    const groups = groupCommands(rankCommands(ALL, "levell"));
    expect(groups).toHaveLength(1);
    expect(groups[0].group).toBe("Library");
    expect(groups[0].commands.map((c) => c.id)).toEqual(["series:1"]);
  });

  it("orders sections by their best hit", () => {
    // "s" matches Settings, Sign out and Solo Levelling; whichever scored
    // highest decides which section leads.
    const ranked = rankCommands(ALL, "s");
    const groups = groupCommands(ranked);
    expect(groups[0].group).toBe(ranked[0].group);
  });

  it("preserves every ranked command exactly once", () => {
    const ranked = rankCommands(ALL, "o");
    const flattened = groupCommands(ranked).flatMap((g) => g.commands);
    expect(flattened.map((c) => c.id).sort()).toEqual(
      ranked.map((c) => c.id).sort(),
    );
  });
});
