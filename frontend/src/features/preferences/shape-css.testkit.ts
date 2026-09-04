/**
 * Reads the shipped SHAPE tokens back out of the CSS, for the preset suites.
 *
 * Sibling of `theme-css.testkit.ts`, and for the same reason: the design
 * system's two halves are data expressed as custom properties, and a
 * regression in either is invisible in review. The theme kit parses colour
 * roles (`--mm-*`) out of `globals.css` and `themes.generated.css`; this one
 * parses shape roles (`--shape-*`, and the Tailwind scale tokens a preset is
 * allowed to move) out of the stylesheets that declare them.
 *
 * Test-only. Named `.testkit.ts` rather than `.test.ts` so vitest treats it as
 * a helper and not as a suite with no assertions; it uses `node:fs` and must
 * never be imported by application code.
 */

import { readFileSync } from "node:fs";
import path from "node:path";

const APP = path.resolve(__dirname, "../../app");

export const GLOBALS_CSS = readFileSync(path.join(APP, "globals.css"), "utf8");

const SOURCES: readonly string[] = [GLOBALS_CSS];

/** The raw body of the first rule whose selector starts with `selector`. */
export function shapeRuleBody(selector: string): string {
  for (const css of SOURCES) {
    const start = css.indexOf(selector);
    if (start < 0) continue;
    const open = css.indexOf("{", start);
    return css.slice(open + 1, css.indexOf("}", open));
  }
  throw new Error(`selector not found in the shape stylesheets: ${selector}`);
}

/** Every custom-property declaration inside a rule body, in source order. */
export function declarationsIn(body: string): Record<string, string> {
  const declarations: Record<string, string> = {};
  // Values can contain `(` … `)` with commas and nested `var()`, but never a
  // `;` outside a string, and this stylesheet has no strings in a custom
  // property. Splitting on `;` is therefore exact here.
  for (const line of body.split(";")) {
    const match = /(--[a-z0-9-]+)\s*:\s*([\s\S]+)/i.exec(line.trim());
    if (match) declarations[match[1]] = match[2].replace(/\s+/g, " ").trim();
  }
  return declarations;
}

/** Every custom property a rule declares. */
export function declarationBlock(selector: string): Record<string, string> {
  return declarationsIn(shapeRuleBody(selector));
}

/**
 * The `--shape-*` defaults: the second bare `:root {` in globals.css.
 *
 * The FIRST one is the colour base (see `theme-css.testkit.ts`), so this skips
 * past it. Two blocks rather than one is deliberate in the stylesheet — the
 * vocabularies are kept visually apart — and this is the cost of that choice,
 * paid once, here.
 */
export function shapeBaseBlock(): Record<string, string> {
  const first = GLOBALS_CSS.indexOf(":root {");
  const second = GLOBALS_CSS.indexOf(":root {", first + 1);
  if (second < 0) throw new Error("globals.css has no shape-role :root block");
  const open = GLOBALS_CSS.indexOf("{", second);
  return declarationsIn(GLOBALS_CSS.slice(open + 1, GLOBALS_CSS.indexOf("}", open)));
}

/**
 * Whether a declaration value names a colour outright.
 *
 * This is the mechanical half of "a preset must not hard-code a colour". A
 * `var(--mm-…)` reference is fine — that is a preset choosing which theme role
 * paints something, which is exactly the indirection the split exists for.
 */
export function containsColourLiteral(value: string): boolean {
  return /#[0-9a-f]{3,8}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\s*\(/i.test(
    value,
  );
}

/** Every `:root[data-theme="…"]` selector present in globals.css. */
export function themeSelectorsInGlobals(): string[] {
  return [...GLOBALS_CSS.matchAll(/:root\[data-theme="([a-z0-9-]+)"\]/gi)].map(
    (match) => match[0],
  );
}

/** How many times `token` is read (as `var(--token…)`) across both files. */
export function referenceCount(token: string): number {
  const needle = `var(${token})`;
  return SOURCES.reduce(
    (total, css) => total + css.split(needle).length - 1,
    0,
  );
}
