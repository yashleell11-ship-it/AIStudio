import { describe, expect, it } from "vitest";
import { DESIGN_PRESETS } from "./presets";
import { declarationBlock, shapeBaseBlock } from "./shape-css.testkit";

/**
 * A preset cannot lower a contrast ratio — it never touches a colour — but it
 * CAN invalidate one.
 *
 * WCAG has two thresholds, and which one applies is decided by SIZE. Body text
 * needs 4.5:1; text that is large (≥ 24px, or ≥ 18.66px bold) needs only 3:1.
 * `theme-contrast.test.ts` holds the hero gradient to the large-text floor
 * precisely because `.hero-heading` is display sized. Shrink that heading past
 * 24px in a preset and the 3:1 the palette was certified at stops being
 * enough — a real accessibility regression produced entirely by a change to
 * shape, in a file where no colour appears.
 *
 * So the preset system carries its own floors, and they are the shape-side
 * mirror of the palette-side ones:
 *
 *   - anything gated at 3:1 must still RENDER at large-text size;
 *   - anything gated at 4.5:1 must still be readable, which is a separate
 *     argument from contrast but fails the same way if ignored.
 *
 * These are not the contrast test. They are what stops a preset from quietly
 * defeating it.
 */

/** The CSS px value of a `rem` length, at the app's 16px root. */
function rem(value: string): number {
  const match = /^([0-9.]+)rem$/.exec(value.trim());
  if (match === null) throw new Error(`not a rem length: ${value}`);
  return Number(match[1]) * 16;
}

const SHAPE_BASE = shapeBaseBlock();

/**
 * Tailwind's own type ramp, which is what a preset that declares no `--text-*`
 * renders at. Restated here rather than parsed: these are upstream defaults,
 * not app source, and a test that read them from `node_modules` would be
 * asserting that Tailwind still ships what Tailwind ships.
 */
const TAILWIND_TEXT: Record<string, string> = {
  "--text-xs": "0.75rem",
  "--text-sm": "0.875rem",
  "--text-base": "1rem",
  "--text-lg": "1.125rem",
  "--text-xl": "1.25rem",
  "--text-2xl": "1.5rem",
  "--text-3xl": "1.875rem",
  "--text-4xl": "2.25rem",
  "--text-5xl": "3rem",
  "--text-6xl": "3.75rem",
};

/** WCAG 2.1's large-text boundary for regular weight, in px. */
const LARGE_TEXT_PX = 24;

/**
 * The smallest this interface is willing to set body copy, in px.
 *
 * Not a WCAG number — WCAG has no minimum size — but the point past which the
 * 4.5:1 the palettes are certified at stops describing anything anyone can
 * read. Compact sits exactly on it at `--text-sm`.
 */
const BODY_FLOOR_PX = 13;

/** The resolved type ramp and title size a viewer on `preset` gets. */
function scaleFor(preset: string): Record<string, string> {
  const block = declarationBlock(`:root[data-preset="${preset}"]`);
  return { ...TAILWIND_TEXT, ...SHAPE_BASE, ...block };
}

describe.each(DESIGN_PRESETS)("%s preset type scale", (preset) => {
  const scale = scaleFor(preset);

  it("keeps the display steps above the large-text floor", () => {
    // `.hero-heading` is painted from `--mm-hero-from` / `--mm-hero-to`, which
    // every palette clears at 3:1 and not at 4.5:1. It is set with `text-4xl`
    // through `text-6xl`; if a preset dropped those below 24px the gradient
    // would need to clear 4.5:1 instead, and roughly half the library would
    // stop qualifying.
    for (const step of ["--text-4xl", "--text-5xl", "--text-6xl"] as const) {
      expect(rem(scale[step]), `${preset} ${step}`).toBeGreaterThanOrEqual(LARGE_TEXT_PX);
    }
  });

  it("keeps the page title above the large-text floor", () => {
    // `.page-title` is the other display-sized surface, and it is the one a
    // preset is most tempted to shrink.
    expect(rem(scale["--shape-title-size"]), preset).toBeGreaterThanOrEqual(
      LARGE_TEXT_PX,
    );
  });

  it("keeps body copy readable", () => {
    for (const step of ["--text-sm", "--text-base"] as const) {
      expect(rem(scale[step]), `${preset} ${step}`).toBeGreaterThanOrEqual(
        BODY_FLOOR_PX,
      );
    }
  });

  it("never shrinks the smallest step the app uses for text", () => {
    // `text-xs` is already at the bottom: status badges, counts, credit lines.
    // A density preset that took it lower would be trading legibility for rows,
    // which is the trade this system is not allowed to make.
    expect(rem(scale["--text-xs"]), preset).toBeGreaterThanOrEqual(
      rem(TAILWIND_TEXT["--text-xs"]),
    );
  });

  it("keeps the ramp monotonic", () => {
    // A preset that reordered two steps would make `text-lg` smaller than
    // `text-base` somewhere in the app, which reads as a rendering bug.
    const steps = Object.keys(TAILWIND_TEXT).map((step) => rem(scale[step]));
    for (let index = 1; index < steps.length; index += 1) {
      expect(steps[index], `${preset} step ${index}`).toBeGreaterThanOrEqual(
        steps[index - 1],
      );
    }
  });
});

describe("preset density floors", () => {
  it("keeps the spacing unit within a range the layout survives", () => {
    // `--spacing` scales padding, gaps AND icon sizes together, which is what
    // makes a density change look designed. It is also the one token that can
    // break a layout outright, so the range is narrow and asserted.
    for (const preset of DESIGN_PRESETS) {
      const declared = declarationBlock(`:root[data-preset="${preset}"]`)["--spacing"];
      if (declared === undefined) continue;
      const px = rem(declared);
      expect(px, `${preset} --spacing`).toBeGreaterThanOrEqual(3.2);
      expect(px, `${preset} --spacing`).toBeLessThanOrEqual(4.8);
    }
  });

  it("leaves every preset a usable page margin", () => {
    for (const preset of DESIGN_PRESETS) {
      const scale = scaleFor(preset);
      expect(rem(scale["--shape-page-pad"]), `${preset} page pad`).toBeGreaterThanOrEqual(
        8,
      );
      expect(
        rem(scale["--shape-page-measure"]),
        `${preset} measure`,
      ).toBeGreaterThanOrEqual(64 * 16);
    }
  });
});
