import { readFileSync, readdirSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Tags are not a feature of the web client, and this pins that.
 *
 * The backend keeps tag CRUD (`/library/tags`, `/library/series-tags`) and the
 * client once bound all five calls, but nothing ever *read* a tag back: no
 * series payload carries its tags (`FollowedSeriesService.serialize`) and
 * `GET /library/series` has no `tag_id` filter, so an attached tag was
 * invisible everywhere and unfindable by. What shipped was a "+ Tag" button
 * that opened a list only a never-called `createTag` could fill, and a bulk
 * control permanently disabled next to it.
 *
 * Re-adding the mutations alone would rebuild that dead end, so the guard is
 * on the request builders rather than on the buttons: whoever brings tags back
 * has to delete this test, and reading it tells them the read path is the part
 * that was missing.
 */

const SURFACE =
  /\buseTags\b|\buseCreateTag\b|\buseDeleteTag\b|\buseAddTagToSeries\b|\buseRemoveTagFromSeries\b|\blistTags\b|\bcreateTag\b|\bdeleteTag\b|\baddTagToSeries\b|\bremoveTagFromSeries\b|\/library\/tags|\/library\/series-tags/;

function sourceFiles(dir: URL): { name: string; text: string }[] {
  const out: { name: string; text: string }[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const child = new URL(`${entry.name}${entry.isDirectory() ? "/" : ""}`, dir);
    if (entry.isDirectory()) {
      out.push(...sourceFiles(child));
      continue;
    }
    if (!/\.tsx?$/.test(entry.name) || entry.name.endsWith(".test.ts")) continue;
    out.push({ name: entry.name, text: readFileSync(child, "utf8") });
  }
  return out;
}

describe("library client tag surface", () => {
  const files = sourceFiles(new URL("./", import.meta.url));

  it("reads its own sources", () => {
    expect(files.length).toBeGreaterThan(10);
    expect(files.map((f) => f.name)).toContain("api.ts");
    expect(files.map((f) => f.name)).toContain("hooks.ts");
  });

  it("binds no tag endpoint anywhere under features/library", () => {
    const offenders = files.filter((f) => SURFACE.test(f.text)).map((f) => f.name);
    expect(offenders).toEqual([]);
  });
});
