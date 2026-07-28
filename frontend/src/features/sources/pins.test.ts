import { describe, expect, it } from "vitest";
import {
  isSourcePinned,
  removeSourcePin,
  toggleSourcePin,
  unpinnedSources,
} from "./pins";
import type { SourcePin, SourceSummary } from "./types";

function pin(sourceId: string, sortOrder: number): SourcePin {
  return {
    source_id: sourceId,
    sort_order: sortOrder,
    name: sourceId,
    icon_url: null,
    mature: false,
    available: true,
  };
}

function source(id: string, overrides: Partial<SourceSummary> = {}): SourceSummary {
  return {
    id,
    name: id,
    description: "",
    browsable: true,
    supports_import: false,
    icon_url: null,
    ...overrides,
  };
}

describe("isSourcePinned", () => {
  it("detects a pinned source", () => {
    expect(isSourcePinned([pin("mangadex", 0)], "mangadex")).toBe(true);
    expect(isSourcePinned([pin("mangadex", 0)], "toonily")).toBe(false);
  });
});

describe("toggleSourcePin", () => {
  it("appends a newly pinned source last, so existing shortcuts keep their order", () => {
    const next = toggleSourcePin([pin("mangadex", 0)], source("toonily"));
    expect(next.map((entry) => entry.source_id)).toEqual(["mangadex", "toonily"]);
    expect(next.map((entry) => entry.sort_order)).toEqual([0, 1]);
  });

  it("carries the source's display name and icon onto the optimistic row", () => {
    const next = toggleSourcePin([], source("toonily", { name: "Toonily", icon_url: "/i.png" }));
    expect(next[0]).toMatchObject({
      source_id: "toonily",
      name: "Toonily",
      icon_url: "/i.png",
      available: true,
    });
  });

  it("unpins an already pinned source and closes the gap in sort_order", () => {
    const pins = [pin("a", 0), pin("b", 1), pin("c", 2)];
    const next = toggleSourcePin(pins, source("b"));
    expect(next.map((entry) => entry.source_id)).toEqual(["a", "c"]);
    // The endpoint rewrites sort_order from array position; keep the optimistic
    // rows consistent with what comes back.
    expect(next.map((entry) => entry.sort_order)).toEqual([0, 1]);
  });

  it("does not mutate the input set", () => {
    const pins = [pin("a", 0)];
    toggleSourcePin(pins, source("b"));
    expect(pins).toHaveLength(1);
  });
});

describe("removeSourcePin", () => {
  it("clears a pin whose source no longer resolves", () => {
    const pins = [pin("a", 0), { ...pin("ghost", 1), available: false }, pin("c", 2)];
    const next = removeSourcePin(pins, "ghost");
    expect(next.map((entry) => entry.source_id)).toEqual(["a", "c"]);
    expect(next.map((entry) => entry.sort_order)).toEqual([0, 1]);
  });

  it("leaves the set untouched when the id is not pinned", () => {
    const pins = [pin("a", 0)];
    expect(removeSourcePin(pins, "nope")).toEqual(pins);
  });
});

describe("unpinnedSources", () => {
  it("returns the installed sources that are not pinned, in order", () => {
    const sources = [source("a"), source("b"), source("c")];
    expect(unpinnedSources(sources, [pin("b", 0)]).map((entry) => entry.id)).toEqual([
      "a",
      "c",
    ]);
  });

  it("ignores pins that no longer match an installed source", () => {
    const sources = [source("a")];
    expect(unpinnedSources(sources, [pin("ghost", 0)]).map((entry) => entry.id)).toEqual([
      "a",
    ]);
  });
});
