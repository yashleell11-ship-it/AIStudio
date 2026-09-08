import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Every cover in the app fades in, and nothing quietly opts out.
 *
 * The fade lives in `CoverImage`, so a new surface that reaches for
 * `next/image` directly gets a cover that snaps to full opacity while every
 * cover beside it fades. That is invisible in review and obvious on screen, so
 * it is asserted here instead: the raw import is allowed in exactly two files
 * and a third one has to justify itself by being added to this list.
 */
const SRC = join(process.cwd(), "src");

/** The wrapper itself, and the reader. */
const ALLOWED = new Set([
  // Wraps next/image; it is the thing every other caller uses instead.
  "components/ui/cover-image.tsx",
  // The reading surface. The strip measures each page's decoded height to keep
  // the reader's place, and an opacity transition there animates nothing that
  // matters while adding a compositing layer per page.
  "features/reader/components/PageImage.tsx",
]);

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

describe("cover fade census", () => {
  const files = walk(SRC);

  it("finds the source tree", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("routes every cover through CoverImage", () => {
    const offenders = files
      .filter((file) => readFileSync(file, "utf8").includes('from "next/image"'))
      .map((file) => file.slice(SRC.length + 1))
      .filter((rel) => !ALLOWED.has(rel));

    expect(offenders).toEqual([]);
  });

  it("keeps the fade in CSS so reduced motion and the preset both reach it", () => {
    const css = readFileSync(join(SRC, "app", "globals.css"), "utf8");
    expect(css).toContain("[data-cover]");
    expect(css).toContain("[data-cover][data-cover-settled=\"true\"]");
    // The duration must ride the preset multiplier, not be hardcoded.
    expect(css).toMatch(/\[data-cover\][\s\S]*?var\(--shape-motion\)/);
    // Both properties named, or the hover scale loses its transition.
    expect(css).toMatch(
      /\[data-cover\][\s\S]*?transition-property:\s*opacity,\s*transform/,
    );
  });
});
