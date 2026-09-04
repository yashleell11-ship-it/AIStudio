#!/usr/bin/env node
/**
 * Refresh `base16-cache.json` from the upstream scheme corpus.
 *
 * The palettes this app ships are NOT hand-picked hexes: they are generated
 * from `tinted-theming/schemes`, the canonical base16 collection (Gruvbox,
 * Nord, Dracula, Catppuccin, Tokyo Night, Everforest, Kanagawa, Rosé Pine,
 * Solarized, Ayu, Monokai, One Dark and ~330 more). Copying colours by hand is
 * how a theme picker ends up with typos nobody can review; this fetches them.
 *
 * A shallow `git clone` rather than the GitHub contents API on purpose: the API
 * is rate-limited per IP and 338 file reads blow through the anonymous budget
 * on the first run.
 *
 * The cache is COMMITTED so `build-themes.mjs` is reproducible offline and so a
 * diff to a shipped palette is reviewable as a data change. Re-run this only to
 * pick up upstream additions.
 *
 *   node scripts/themes/fetch-base16.mjs
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = "https://github.com/tinted-theming/schemes.git";
const CACHE = path.join(HERE, "base16-cache.json");

/**
 * Minimal YAML reader for the one shape these files have: four scalar keys and
 * a flat `palette:` block. Pulling a YAML dependency into the frontend to read
 * 338 files of `key: "value"` would be the larger cost.
 */
function parseScheme(text) {
  const scalars = {};
  const palette = {};
  let inPalette = false;
  for (const rawLine of text.split("\n")) {
    if (/^palette\s*:/.test(rawLine)) {
      inPalette = true;
      continue;
    }
    if (inPalette) {
      const entry = /^\s+(base0[0-9A-F])\s*:\s*"?(#[0-9a-fA-F]{6})/.exec(rawLine);
      if (entry) {
        palette[entry[1]] = entry[2].toLowerCase();
        continue;
      }
      if (/^\S/.test(rawLine)) inPalette = false;
    }
    const scalar = /^([a-z_]+)\s*:\s*(.*)$/.exec(rawLine);
    if (!scalar) continue;
    const [, key, rest] = scalar;
    if (key === "palette") continue;
    // Quoted values may contain `#` (author URLs, notes); unquoted ones end at
    // a trailing comment.
    const quoted = /^"((?:[^"\\]|\\.)*)"/.exec(rest.trim());
    scalars[key] = quoted ? quoted[1] : rest.split("#")[0].trim();
  }
  return { ...scalars, palette };
}

const work = mkdtempSync(path.join(tmpdir(), "base16-"));
try {
  execFileSync("git", ["clone", "--depth", "1", "--quiet", REPO, work], {
    stdio: ["ignore", "ignore", "inherit"],
  });
  const revision = execFileSync("git", ["-C", work, "rev-parse", "HEAD"], {
    encoding: "utf8",
  }).trim();

  const dir = path.join(work, "base16");
  const schemes = {};
  let skipped = 0;
  for (const file of readdirSync(dir).sort()) {
    if (!/\.ya?ml$/.test(file)) continue;
    const slug = file.replace(/\.ya?ml$/, "");
    const parsed = parseScheme(readFileSync(path.join(dir, file), "utf8"));
    const bases = Object.keys(parsed.palette);
    if (bases.length !== 16 || !parsed.name) {
      skipped += 1;
      continue;
    }
    schemes[slug] = {
      name: parsed.name,
      author: parsed.author ?? "",
      variant: parsed.variant === "light" ? "light" : "dark",
      palette: parsed.palette,
    };
  }

  writeFileSync(
    CACHE,
    `${JSON.stringify(
      {
        source: "https://github.com/tinted-theming/schemes",
        revision,
        fetchedAt: new Date().toISOString().slice(0, 10),
        count: Object.keys(schemes).length,
        schemes,
      },
      null,
      2,
    )}\n`,
  );
  console.log(
    `base16-cache.json: ${Object.keys(schemes).length} schemes @ ${revision.slice(0, 8)}` +
      (skipped ? ` (${skipped} malformed, skipped)` : ""),
  );
} finally {
  rmSync(work, { recursive: true, force: true });
}
