import { describe, expect, it } from "vitest";
import { sourceSections } from "./source-filter";
import type { SourcePin, SourceSummary } from "./types";

function source(overrides: Partial<SourceSummary> & { id: string }): SourceSummary {
  return {
    name: overrides.id,
    description: "",
    browsable: true,
    supports_import: true,
    icon_url: null,
    ...overrides,
  };
}

function pin(source_id: string, overrides: Partial<SourcePin> = {}): SourcePin {
  return {
    source_id,
    sort_order: 0,
    name: source_id,
    icon_url: null,
    mature: false,
    available: true,
    ...overrides,
  };
}

const SOURCES = [
  source({ id: "asurascans", name: "Asura Scans" }),
  source({ id: "mangadex", name: "MangaDex" }),
  source({ id: "nhentai", name: "nhentai", mature: true }),
];

describe("sourceSections", () => {
  it("puts pinned sources in their own section, in the server's pin order", () => {
    const { pinned, rest } = sourceSections({
      sources: SOURCES,
      pins: [pin("mangadex", { sort_order: 0 }), pin("asurascans", { sort_order: 1 })],
      query: "",
      filter: "all",
    });

    expect(pinned.map((r) => r.source.id)).toEqual(["mangadex", "asurascans"]);
    expect(rest.map((s) => s.id)).toEqual(["nhentai"]);
  });

  it("keeps a pin whose source no longer resolves, marked unavailable", () => {
    // Removed, renamed, or hidden by the 18+ gate. It has to stay visible or
    // there is no way to clear it from an ordering the reader arranged.
    const { pinned } = sourceSections({
      sources: SOURCES,
      pins: [pin("deadsource", { name: "Dead Source" })],
      query: "",
      filter: "all",
    });

    expect(pinned).toHaveLength(1);
    expect(pinned[0].unavailable).toBe(true);
    expect(pinned[0].source.name).toBe("Dead Source");
  });

  it("matches on both display name and connector id", () => {
    expect(
      sourceSections({ sources: SOURCES, pins: [], query: "asura", filter: "all" }).rest.map(
        (s) => s.id,
      ),
    ).toEqual(["asurascans"]);

    expect(
      sourceSections({ sources: SOURCES, pins: [], query: "MangaDex", filter: "all" }).rest.map(
        (s) => s.id,
      ),
    ).toEqual(["mangadex"]);
  });

  it("empties the unpinned list under the Pinned scope rather than filtering it", () => {
    // Everything in `rest` is unpinned by definition, so filtering it would
    // leave the chip inert while still rendering every row under "All sources".
    const { pinned, rest } = sourceSections({
      sources: SOURCES,
      pins: [pin("mangadex")],
      query: "",
      filter: "pinned",
    });

    expect(pinned.map((r) => r.source.id)).toEqual(["mangadex"]);
    expect(rest).toEqual([]);
  });

  it("shows only 18+ connectors under the mature scope", () => {
    const { rest } = sourceSections({
      sources: SOURCES,
      pins: [],
      query: "",
      filter: "mature",
    });

    expect(rest.map((s) => s.id)).toEqual(["nhentai"]);
  });

  it("preserves the backend's ordering rather than re-sorting", () => {
    // Re-sorting client-side with a plain string compare put every lowercase id
    // after every uppercase one; /sources is already case-insensitively ordered.
    const ordered = [
      source({ id: "apcomics", name: "APComics" }),
      source({ id: "asurascans", name: "Asura Scans" }),
      source({ id: "bato", name: "bato" }),
      source({ id: "Cocomic", name: "Cocomic" }),
    ];

    expect(
      sourceSections({ sources: ordered, pins: [], query: "", filter: "all" }).rest.map(
        (s) => s.id,
      ),
    ).toEqual(["apcomics", "asurascans", "bato", "Cocomic"]);
  });
});
