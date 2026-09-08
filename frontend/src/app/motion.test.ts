import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The app's CSS motion contract.
 *
 * These are the rules that are easy to get subtly wrong and impossible to
 * notice in review, because every one of them looks fine in the diff and only
 * misbehaves on screen. Each assertion here corresponds to something that was
 * actually measured in a browser.
 */
const css = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

/**
 * The declaration body of a top-level class rule, comments stripped.
 *
 * These rules carry long comments explaining which fill modes are wrong and
 * why, so a naive substring search finds `both` in the prose arguing against
 * it. Only the declarations are the contract.
 */
function rule(selector: string): string {
  const start = css.indexOf(`${selector} {`);
  expect(start, `${selector} is missing from globals.css`).toBeGreaterThan(-1);
  return css
    .slice(start, css.indexOf("\n}", start))
    .replace(/\/\*[\s\S]*?\*\//g, "");
}

/** The body of a `@keyframes` block. */
function keyframes(name: string): string {
  const start = css.indexOf(`@keyframes ${name}`);
  expect(start, `@keyframes ${name} is missing`).toBeGreaterThan(-1);
  return css.slice(start, css.indexOf("\n}", start));
}

const ANIMATED = [
  ".content-in",
  ".stagger-in > *",
  ".overlay-in",
  ".panel-in",
  ".sheet-up-in",
  ".route-in",
];

describe("motion contract", () => {
  it.each(ANIMATED)("%s scales with the design preset", (selector) => {
    expect(rule(selector)).toContain("var(--shape-motion)");
  });

  it("staggered children hold their first frame while they wait", () => {
    // Without this the delayed buckets show their NORMAL style during the
    // delay, so a card in the fourth row appeared, vanished the instant its
    // animation started, and only then faded in. Measured at 90ms before the
    // fix: the 27th child sat at opacity 1. After: 0.
    expect(rule(".stagger-in > *")).toContain("animation-fill-mode: backwards");
  });

  it("nothing pins an end state, so content is visible if animation never runs", () => {
    // `both` / `forwards` would strand an element on its `from` frame in a
    // paused tab or a browser that never produced a frame. `backwards` only
    // fills the pre-delay phase and is checked above.
    for (const selector of ANIMATED) {
      expect(rule(selector), selector).not.toMatch(/\b(both|forwards)\b/);
    }
  });

  it("the route fade never transforms the app's only scroller", () => {
    // A transform on `main` makes it the containing block for every fixed
    // descendant, which would quietly move the bulk action bar and tab pill.
    expect(keyframes("route-in")).not.toContain("transform");
  });

  it("the route fade starts part-way, so the shell never flashes empty", () => {
    expect(keyframes("route-in")).toMatch(/opacity:\s*0\.\d/);
  });

  it("the cascade is capped so a long grid does not keep counting", () => {
    // The last bucket is open-ended (`n + 25`), so the 200th cover waits the
    // same 240ms as the 25th rather than a couple of seconds.
    expect(css).toContain(".stagger-in > :nth-child(n + 25)");
  });

  it("reduced motion still overrides everything above", () => {
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
  });
});
