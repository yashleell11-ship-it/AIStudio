/**
 * Reads the shipped palettes back out of the CSS, for the theme test suites.
 *
 * The palettes are the one part of the design system where a regression is
 * invisible in review — a hex is a hex — so the tests assert against what the
 * browser will actually load rather than against the TypeScript that describes
 * it. That means parsing CSS, and it means parsing BOTH files: the four
 * hand-written palettes live in `globals.css` and the generated ones in
 * `themes.generated.css`, and a test that knew about only one of them would
 * silently stop covering thirty-eight themes.
 *
 * Test-only. Named `.testkit.ts` rather than `.test.ts` so vitest treats it as
 * a helper and not as a suite with no assertions; it uses `node:fs` and must
 * never be imported by application code.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { DEFAULT_READING_THEME, type ReadingTheme } from "./theme";

const HAND_WRITTEN = readFileSync(
  path.resolve(__dirname, "../../app/globals.css"),
  "utf8",
);
const GENERATED = readFileSync(
  path.resolve(__dirname, "../../app/themes.generated.css"),
  "utf8",
);

/** Both stylesheets, in the order the browser sees them. */
export const THEME_CSS_SOURCES = { HAND_WRITTEN, GENERATED } as const;

/** The raw body of the first rule whose selector starts with `selector`. */
export function ruleBody(selector: string): string {
  for (const css of [HAND_WRITTEN, GENERATED]) {
    const start = css.indexOf(selector);
    if (start < 0) continue;
    const open = css.indexOf("{", start);
    return css.slice(open + 1, css.indexOf("}", open));
  }
  throw new Error(`selector not found in either stylesheet: ${selector}`);
}

/** Every `--mm-*` declaration inside that rule. */
export function roleBlock(selector: string): Record<string, string> {
  const roles: Record<string, string> = {};
  for (const line of ruleBody(selector).split(";")) {
    const match = /(--mm-[a-z0-9-]+)\s*:\s*([^;]+)/i.exec(line);
    if (match) roles[match[1]] = match[2].trim();
  }
  return roles;
}

/** The role defaults every theme overrides — and the default theme's palette. */
export const BASE_ROLES = roleBlock(":root {");

/**
 * The fully resolved role set a viewer on `theme` gets: its own declarations
 * over the `:root` defaults.
 *
 * The default theme resolves to the defaults themselves. It also has a block of
 * its own in the generated stylesheet (it is a normal palette anyone can pick
 * by name), and the two are required to be identical — `theme.test.ts` asserts
 * that separately, which is the only reason it is safe to short-circuit here.
 */
export function paletteFor(theme: ReadingTheme): Record<string, string> {
  if (theme === DEFAULT_READING_THEME) return BASE_ROLES;
  return { ...BASE_ROLES, ...roleBlock(`:root[data-theme="${theme}"]`) };
}
