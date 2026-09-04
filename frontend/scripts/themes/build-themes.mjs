#!/usr/bin/env node
/**
 * Turn the base16 cache into the two files the app actually ships:
 *
 *   src/app/themes.generated.css              one `:root[data-theme=…]` block each
 *   src/features/preferences/themes.generated.ts   ids, labels and swatches
 *
 * and one file nobody ships but everybody should be able to read:
 *
 *   scripts/themes/audit.json   every one of the 338, gate verdict and why
 *
 * Both outputs are generated together from the same mapping so they cannot
 * drift: a swatch that paints a colour the CSS does not set would be a picker
 * that lies about what it is about to do.
 *
 * Run after editing `curated.mjs` or `map.mjs`:
 *   node scripts/themes/build-themes.mjs
 */
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { CURATED, CURATED_DARK, CURATED_LIGHT } from "./curated.mjs";
import { mapScheme, verifyRoles } from "./map.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const cache = JSON.parse(readFileSync(path.join(HERE, "base16-cache.json"), "utf8"));

/** Theme ids owned by the hand-written palettes in globals.css. */
const RESERVED = new Set(["dark", "midnight", "sepia", "light"]);

// ---------------------------------------------------------------------------
// gate every scheme (for the audit), then build the curated ones
// ---------------------------------------------------------------------------

const audit = { total: 0, passed: 0, rejected: 0, shipped: 0, schemes: {} };
const built = new Map();

for (const [slug, scheme] of Object.entries(cache.schemes)) {
  audit.total += 1;
  const mapped = mapScheme(scheme);
  if (!mapped.ok) {
    audit.rejected += 1;
    audit.schemes[slug] = { verdict: "rejected", reason: mapped.reason };
    continue;
  }
  const failures = verifyRoles(mapped.roles);
  if (failures.length > 0) {
    audit.rejected += 1;
    audit.schemes[slug] = { verdict: "rejected", reason: failures.join("; ") };
    continue;
  }
  audit.passed += 1;
  audit.schemes[slug] = { verdict: "passed", notes: mapped.notes };
  built.set(slug, mapped);
}

/**
 * The credit line for a tile.
 *
 * Upstream `author` fields are addresses as much as names — emails in angle
 * brackets, repository URLs in parentheses, and a few that are nothing BUT a
 * URL. Rendered raw they truncate to "Dawid Kurek (dawikur@gmail.com), morhe…",
 * which credits nobody and looks like a bug. This keeps the human names and, for
 * a bare URL, the account it points at, which is the name that project goes by.
 */
function creditFor(author) {
  /** "https://github.com/catppuccin/catppuccin" → "catppuccin". */
  const accountOf = (url) => {
    const match = /https?:\/\/[^/\s]+\/([^/\s)]+)/.exec(url);
    return match ? match[1] : null;
  };

  const text = author
    // Parentheses and angle brackets in this corpus hold an email or a repo
    // link every time; the name is always outside them.
    .replace(/\s*[([<][^)\]>]*[)\]>]/g, (group) =>
      /@|https?:/.test(group) ? "" : group,
    )
    // Bare URLs stand in for a name rather than annotating one.
    .replace(/https?:\/\/\S+/g, (url) => accountOf(url) ?? "")
    .replace(/\s+/g, " ")
    .replace(/\s+,/g, ",")
    .replace(/([,/])\s*(?=[,/])/g, "")
    .replace(/^[\s,/]+|[\s,/]+$/g, "")
    .trim();

  return text === "" ? author : text;
}

const themes = [];
for (const entry of CURATED) {
  const scheme = cache.schemes[entry.slug];
  if (!scheme) throw new Error(`curated scheme is not in the cache: ${entry.slug}`);
  const mapped = built.get(entry.slug);
  // A curated scheme that fails the gate is a decision to revisit, not a
  // warning to scroll past — the whole point of curating on top of a gate is
  // that both halves have to agree.
  if (!mapped) {
    throw new Error(
      `curated scheme fails the contrast gate: ${entry.slug} — ${audit.schemes[entry.slug].reason}`,
    );
  }
  if (RESERVED.has(entry.slug)) {
    throw new Error(`curated slug collides with a hand-written theme: ${entry.slug}`);
  }
  audit.schemes[entry.slug].verdict = "shipped";
  audit.shipped += 1;
  themes.push({
    id: entry.slug,
    label: entry.label ?? scheme.name,
    blurb: entry.blurb,
    author: creditFor(scheme.author),
    scheme: mapped.scheme,
    roles: mapped.roles,
    notes: mapped.notes,
  });
}

const duplicateLabels = themes
  .map((t) => t.label)
  .filter((label, index, all) => all.indexOf(label) !== index);
if (duplicateLabels.length > 0) {
  throw new Error(`two themes share a label: ${duplicateLabels.join(", ")}`);
}

// ---------------------------------------------------------------------------
// emit
// ---------------------------------------------------------------------------

const banner = (file) => `/*
 * ${file} — GENERATED, do not edit.
 *
 * Source:    ${cache.source}
 * Revision:  ${cache.revision}
 * Regenerate: node scripts/themes/build-themes.mjs
 *
 * ${audit.shipped} palettes, mapped from base16 by scripts/themes/map.mjs and gated at
 * WCAG AA. ${audit.passed} of the corpus's ${audit.total} schemes clear the gate;
 * scripts/themes/curated.mjs picks which of those are worth a tile.
 */`;

const ROLE_ORDER = [
  "--mm-bg",
  "--mm-surface",
  "--mm-elevated",
  "--mm-fg",
  "--mm-muted",
  "--mm-border",
  "--mm-contrast-bg",
  "--mm-contrast-fg",
  "--mm-contrast-border",
  "--mm-primary",
  "--mm-primary-hover",
  "--mm-primary-fg",
  "--mm-primary-tint",
  "--mm-accent",
  "--mm-accent-fg",
  "--mm-accent-warm",
  "--mm-danger",
  "--mm-success",
  "--mm-warning",
  "--mm-glass-panel",
  "--mm-glass-card",
  "--mm-glass-border",
  "--mm-hero-from",
  "--mm-hero-to",
  "--mm-scrollbar",
  "--mm-scrollbar-hover",
  "--mm-glow",
  "--mm-glass-shadow",
  "--mm-focus",
];

const cssBlocks = themes.map((theme) => {
  const notes = theme.notes.length > 0 ? `\n * Adjusted: ${theme.notes.join("; ")}.` : "";
  const body = ROLE_ORDER.map((role) => `  ${role}: ${theme.roles[role]};`).join("\n");
  return `/* ${theme.label} — ${theme.author || "unknown"}.${notes} */
:root[data-theme="${theme.id}"] {
  color-scheme: ${theme.scheme};
${body}
}`;
});

writeFileSync(
  path.join(ROOT, "src/app/themes.generated.css"),
  `${banner("themes.generated.css")}

${cssBlocks.join("\n\n")}
`,
);

const swatchOf = (theme) => ({
  bg: theme.roles["--mm-bg"],
  surface: theme.roles["--mm-elevated"],
  fg: theme.roles["--mm-fg"],
  muted: theme.roles["--mm-muted"],
  accent: theme.roles["--mm-primary"],
});

const tsEntries = themes
  .map((theme) => {
    const s = swatchOf(theme);
    return `  {
    id: ${JSON.stringify(theme.id)},
    label: ${JSON.stringify(theme.label)},
    description: ${JSON.stringify(theme.blurb)},
    author: ${JSON.stringify(theme.author)},
    scheme: ${JSON.stringify(theme.scheme)},
    swatch: {
      bg: ${JSON.stringify(s.bg)},
      surface: ${JSON.stringify(s.surface)},
      fg: ${JSON.stringify(s.fg)},
      muted: ${JSON.stringify(s.muted)},
      accent: ${JSON.stringify(s.accent)},
    },
  },`;
  })
  .join("\n");

writeFileSync(
  path.join(ROOT, "src/features/preferences/themes.generated.ts"),
  `${banner("themes.generated.ts")}

import type { GeneratedThemeMeta } from "./theme-types";

/**
 * Ordered dark-first, and within a variant in the order \`curated.mjs\` declares
 * — which groups families together (every Gruvbox next to every other) rather
 * than alphabetising them apart.
 *
 * \`as const satisfies\` rather than a plain annotation: the ids have to survive
 * as literal types so \`ReadingTheme\` stays a closed union and a typo in a
 * \`setTheme("gruvbux")\` call is a compile error rather than a theme that does
 * nothing.
 */
export const GENERATED_THEMES = [
${tsEntries}
] as const satisfies readonly GeneratedThemeMeta[];
`,
);

writeFileSync(
  path.join(HERE, "audit.json"),
  `${JSON.stringify(
    {
      source: cache.source,
      revision: cache.revision,
      generatedFrom: "scripts/themes/map.mjs",
      total: audit.total,
      passedGate: audit.passed,
      rejected: audit.rejected,
      shipped: audit.shipped,
      schemes: audit.schemes,
    },
    null,
    2,
  )}\n`,
);

const reasons = {};
for (const record of Object.values(audit.schemes)) {
  if (record.verdict === "rejected") {
    reasons[record.reason] = (reasons[record.reason] ?? 0) + 1;
  }
}
console.log(
  `themes: ${audit.shipped} shipped (${CURATED_DARK.length} dark, ${CURATED_LIGHT.length} light) ` +
    `· ${audit.passed}/${audit.total} cleared the gate · ${audit.rejected} rejected`,
);
for (const [reason, count] of Object.entries(reasons).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${String(count).padStart(3)}  ${reason}`);
}
