import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  LIBRARY_DISCOVERY_QUERY_ROOT,
  LIBRARY_QUERY_ROOT,
} from "@/features/library/hooks";
import { SOURCES_QUERY_ROOT } from "@/features/sources/hooks";
import {
  MATURE_GATED_QUERY_ROOTS,
  MATURE_TOGGLE_NO_PROFILE_REASON,
  NOT_MATURE_GATED_QUERY_ROOTS,
  invalidateMatureGatedQueries,
  matureToggleBlockReason,
} from "./mature-gate";

describe("matureToggleBlockReason", () => {
  it("allows the write when a profile is active", () => {
    expect(matureToggleBlockReason(3)).toBeNull();
  });

  it("blocks the write with no active profile", () => {
    // PUT /settings retargets the instance-wide default when no X-Profile-Id
    // is attached, so a profile-less write changes every profile's fallback
    // instead of the caller's own setting.
    expect(matureToggleBlockReason(null)).toBe(MATURE_TOGGLE_NO_PROFILE_REASON);
  });

  it("treats profile id 0 as an active profile, not as absent", () => {
    expect(matureToggleBlockReason(0)).toBeNull();
  });
});

describe("invalidateMatureGatedQueries", () => {
  function recorder() {
    const roots: unknown[] = [];
    return {
      roots,
      invalidateQueries: ({ queryKey }: { queryKey: readonly unknown[] }) => {
        roots.push(queryKey[0]);
      },
    };
  }

  it("drops every cache the backend filters by the 18+ gate", () => {
    const client = recorder();
    invalidateMatureGatedQueries(client);
    // `list_series` (and therefore the library grid, the followed index and
    // library search), `continue_reading` and `recommendations` all go through
    // `FollowedSeriesService._visible`, so both library roots have to go.
    expect(client.roots).toContain(LIBRARY_QUERY_ROOT);
    expect(client.roots).toContain(LIBRARY_DISCOVERY_QUERY_ROOT);
    expect(client.roots).toContain(SOURCES_QUERY_ROOT);
    expect(client.roots).toContain("preferences");
  });

  it("names no root that nothing is cached under", () => {
    // `intelligence` was the discovery root before the source-native rewrite
    // renamed it; invalidating it matched nothing and left the gated library
    // caches in place.
    expect(MATURE_GATED_QUERY_ROOTS).not.toContain("intelligence");
  });
});

describe("MATURE_GATED_QUERY_ROOTS covers every cache root in the app", () => {
  const SRC = new URL("../../", import.meta.url).pathname;

  /**
   * Declared roots, read off the source that ships.
   *
   * Two shapes, and the codebase uses only these two: a root named on its own
   * (`const SOURCES_QUERY_ROOT = "sources"`) and a one-element key tuple
   * (`const OCR_KEY = ["ocr"]`). Anchoring on the closing quote keeps dotted
   * storage keys — `mm.active-profile`, `mm.updates.banner.dismissedMaxId` —
   * out: those are localStorage, not query caches.
   */
  const DECLARED =
    /const [A-Z][A-Z0-9_]*(?:_KEY|_QUERY_ROOT|_QUERY_KEY) = (?:\[\s*)?"([a-z][a-z-]*)"/g;
  /** A root written inline at a call site rather than named — `["status", …]`. */
  const INLINE = /queryKey: \[\s*"([a-z][a-z-]*)"/g;

  function sourceFiles(dir: string): string[] {
    const files: string[] = [];
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "node_modules") files.push(...sourceFiles(path));
        continue;
      }
      if (!/\.tsx?$/.test(entry.name) || /\.test\.tsx?$/.test(entry.name)) continue;
      files.push(path);
    }
    return files;
  }

  function declaredRoots(): Map<string, string> {
    const roots = new Map<string, string>();
    for (const file of sourceFiles(SRC)) {
      const source = readFileSync(file, "utf8");
      for (const pattern of [DECLARED, INLINE]) {
        pattern.lastIndex = 0;
        for (const match of source.matchAll(pattern)) {
          if (!roots.has(match[1])) roots.set(match[1], file);
        }
      }
    }
    return roots;
  }

  it("finds the roots it is meant to be checking", () => {
    // A scan that silently matched nothing would pass every assertion below.
    const roots = declaredRoots();
    expect(roots.has("library")).toBe(true);
    expect(roots.has("bookmarks")).toBe(true);
    expect(roots.size).toBeGreaterThanOrEqual(
      MATURE_GATED_QUERY_ROOTS.length + NOT_MATURE_GATED_QUERY_ROOTS.length,
    );
  });

  it("classifies every root as gated or explicitly not gated", () => {
    const classified = new Set<string>([
      ...MATURE_GATED_QUERY_ROOTS,
      ...NOT_MATURE_GATED_QUERY_ROOTS,
    ]);
    const unclassified = [...declaredRoots()]
      .filter(([root]) => !classified.has(root))
      .map(([root, file]) => `${root} (${file})`);
    // Adding a feature with its own cache root now forces the question the
    // gate keeps losing: does the backend filter it by the 18+ setting?
    expect(unclassified).toEqual([]);
  });

  it("puts no root on both lists", () => {
    const gated = new Set<string>(MATURE_GATED_QUERY_ROOTS);
    expect(NOT_MATURE_GATED_QUERY_ROOTS.filter((root) => gated.has(root))).toEqual([]);
  });

  it("invalidates the four roots that had drifted off the list", () => {
    // Each fronts a service that applies the same `mature_tracker_case`
    // predicate to its own table, and each was reachable in one tap from the
    // Settings toggle with its adult rows still cached.
    for (const root of ["bookmarks", "novels", "ocr", "updates"]) {
      expect(MATURE_GATED_QUERY_ROOTS).toContain(root);
    }
  });
});
