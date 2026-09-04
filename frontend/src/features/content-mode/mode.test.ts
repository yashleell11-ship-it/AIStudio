import { describe, expect, it } from "vitest";
import type { SourceSummary } from "@/features/sources/types";
import {
  buildSourceModeIndex,
  CONTENT_MODE_COPY,
  DEFAULT_CONTENT_MODE,
  filterByContentMode,
  filterSourcesByContentMode,
  isContentMode,
  matchesContentMode,
  parseContentMode,
  resolveContentMode,
  sourceContentMode,
} from "./mode";

function source(id: string, kind?: "manga" | "novel"): SourceSummary {
  return {
    id,
    name: id,
    description: "",
    browsable: true,
    supports_import: false,
    ...(kind ? { content_kind: kind } : {}),
  };
}

const SOURCES = [
  source("asurascans", "manga"),
  source("mangadex"), // pre-`content_kind` connector: no field at all
  source("novelarchive", "novel"),
  source("royalroad", "novel"),
];

describe("parseContentMode", () => {
  it("reads a stored choice and rejects anything else", () => {
    expect(parseContentMode("manga")).toBe("manga");
    expect(parseContentMode(" novel ")).toBe("novel");
    expect(parseContentMode("audiobook")).toBeNull();
    expect(parseContentMode(null)).toBeNull();
    expect(isContentMode("novel")).toBe(true);
    expect(isContentMode(3)).toBe(false);
  });
});

describe("resolveContentMode", () => {
  it("defaults to manga — what the library actually holds", () => {
    expect(DEFAULT_CONTENT_MODE).toBe("manga");
    expect(resolveContentMode(null, true)).toBe("manga");
  });

  it("honours a stored choice while novels are enabled", () => {
    expect(resolveContentMode("novel", true)).toBe("novel");
    expect(resolveContentMode("manga", true)).toBe("manga");
  });

  it("forces manga when the server has novels off, whatever is stored", () => {
    // A profile that used Novels mode before the flag was turned off must not
    // come back to a half-empty app.
    expect(resolveContentMode("novel", false)).toBe("manga");
    expect(resolveContentMode(null, false)).toBe("manga");
  });
});

describe("sourceContentMode", () => {
  it("treats an unlabelled connector as manga", () => {
    expect(sourceContentMode(source("mangadex"))).toBe("manga");
    expect(sourceContentMode(undefined)).toBe("manga");
    expect(sourceContentMode(null)).toBe("manga");
  });

  it("reads the declared kind", () => {
    expect(sourceContentMode(source("x", "novel"))).toBe("novel");
    expect(sourceContentMode(source("x", "manga"))).toBe("manga");
  });
});

describe("filterSourcesByContentMode", () => {
  it("splits the listing cleanly — novels never appear beside manga", () => {
    expect(filterSourcesByContentMode(SOURCES, "manga").map((s) => s.id)).toEqual([
      "asurascans",
      "mangadex",
    ]);
    expect(filterSourcesByContentMode(SOURCES, "novel").map((s) => s.id)).toEqual([
      "novelarchive",
      "royalroad",
    ]);
  });

  it("is the identity on a listing with no novel sources", () => {
    const mangaOnly = [source("asurascans", "manga"), source("mangadex")];
    expect(filterSourcesByContentMode(mangaOnly, "manga")).toEqual(mangaOnly);
  });
});

describe("matchesContentMode", () => {
  const index = buildSourceModeIndex(SOURCES);

  it("scopes a row by the source it belongs to", () => {
    expect(matchesContentMode("asurascans", index, "manga")).toBe(true);
    expect(matchesContentMode("asurascans", index, "novel")).toBe(false);
    expect(matchesContentMode("novelarchive", index, "novel")).toBe(true);
    expect(matchesContentMode("novelarchive", index, "manga")).toBe(false);
  });

  it("keeps a row from an unknown source in manga mode rather than hiding it", () => {
    // Removed connector, 18+-gated source, or a listing that has not loaded:
    // hiding these would blank the library on every cold load.
    expect(matchesContentMode("long-gone", index, "manga")).toBe(true);
    expect(matchesContentMode("long-gone", index, "novel")).toBe(false);
    expect(matchesContentMode(null, index, "manga")).toBe(true);
    expect(matchesContentMode(undefined, index, "novel")).toBe(false);
  });

  it("keeps every row in manga mode while the index is still empty", () => {
    const empty = buildSourceModeIndex(undefined);
    for (const id of ["asurascans", "novelarchive", "anything"]) {
      expect(matchesContentMode(id, empty, "manga")).toBe(true);
    }
  });
});

describe("filterByContentMode", () => {
  const index = buildSourceModeIndex(SOURCES);
  const rows = [
    { id: 1, source_id: "asurascans" },
    { id: 2, source_id: "novelarchive" },
    { id: 3, source_id: "mangadex" },
    { id: 4, source_id: "royalroad" },
  ];

  it("keeps only the rows of the active mode", () => {
    expect(
      filterByContentMode(rows, index, "manga", (row) => row.source_id).map((r) => r.id),
    ).toEqual([1, 3]);
    expect(
      filterByContentMode(rows, index, "novel", (row) => row.source_id).map((r) => r.id),
    ).toEqual([2, 4]);
  });

  it("preserves order — the server already decided it", () => {
    const kept = filterByContentMode(rows, index, "manga", (row) => row.source_id);
    expect(kept).toEqual([rows[0], rows[2]]);
  });
});

describe("copy", () => {
  it("names both modes for the switch and the empty states", () => {
    expect(CONTENT_MODE_COPY.manga.label).toBe("Manga");
    expect(CONTENT_MODE_COPY.novel.label).toBe("Novels");
  });
});
