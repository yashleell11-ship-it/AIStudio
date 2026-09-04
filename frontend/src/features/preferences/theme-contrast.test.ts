import { describe, expect, it } from "vitest";
import {
  WCAG_AA_LARGE_TEXT,
  WCAG_AA_NON_TEXT,
  WCAG_AA_NORMAL_TEXT,
  contrastBetween,
} from "@/lib/contrast";
import { paletteFor } from "./theme-css.testkit";
import { READING_THEMES } from "./theme";

/**
 * Contrast budget for every shipped palette, read out of the CSS itself.
 *
 * The palette is the one place where an accessibility regression is invisible
 * in review — a hex is a hex — and the library is now forty-two palettes deep,
 * thirty-eight of them machine-mapped from community base16 schemes. So the
 * ratios are asserted rather than eyeballed: change a token, or change the
 * mapping in `scripts/themes/map.mjs` and regenerate, and this fails with the
 * exact pairing and the number it missed by.
 *
 * This is deliberately a SECOND opinion. The generator runs the same floors at
 * build time and refuses to emit a scheme that misses them; this suite re-reads
 * the emitted CSS and checks it again, so a bug in the generator's own maths
 * cannot certify itself. The two share no code.
 *
 * The threshold used is WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text and
 * for non-text indicators (focus rings, borders that carry meaning).
 */

/** The three backdrops text is drawn on, in every theme. */
const SURFACE_ROLES = ["--mm-bg", "--mm-surface", "--mm-elevated"] as const;

describe.each(READING_THEMES)("%s theme contrast", (theme) => {
  const palette = paletteFor(theme);

  it.each(SURFACE_ROLES)("primary text on %s clears AA", (surface) => {
    const ratio = contrastBetween(palette["--mm-fg"], palette[surface]);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });

  it.each(SURFACE_ROLES)("muted text on %s clears AA", (surface) => {
    // This is the pairing the brief called out: `text-muted` is the app's
    // second-most-used colour and sits on all three surfaces.
    const ratio = contrastBetween(palette["--mm-muted"], palette[surface]);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });

  it.each(SURFACE_ROLES)("accent text on %s clears AA", (surface) => {
    // `text-primary` labels active nav, links and counts — body-sized text, so
    // it is held to the body threshold, not the large-text one.
    const ratio = contrastBetween(palette["--mm-primary"], palette[surface]);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });

  it("text on a filled primary button clears AA", () => {
    const ratio = contrastBetween(palette["--mm-primary-fg"], palette["--mm-primary"]);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });

  it("the inverted contrast band is readable", () => {
    const ratio = contrastBetween(palette["--mm-contrast-fg"], palette["--mm-contrast-bg"]);
    expect(ratio).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
  });

  it("status colours clear AA on the page background", () => {
    for (const role of ["--mm-danger", "--mm-success", "--mm-warning"] as const) {
      const ratio = contrastBetween(palette[role], palette["--mm-bg"]);
      expect(ratio, `${role} on --mm-bg`).toBeGreaterThanOrEqual(WCAG_AA_NORMAL_TEXT);
    }
  });

  it("the focus ring is distinguishable from every surface", () => {
    // A focus indicator is a non-text element: AA asks for 3:1 against what it
    // sits on. An invisible ring is the failure mode this catches.
    for (const surface of SURFACE_ROLES) {
      const ratio = contrastBetween(palette["--mm-focus"], palette[surface]);
      expect(ratio, `--mm-focus on ${surface}`).toBeGreaterThanOrEqual(WCAG_AA_NON_TEXT);
    }
  });

  it("borders are visible against the surfaces they divide", () => {
    // Translucent, so `contrastBetween` flattens it first — which is the point:
    // rgba(221,228,234,0.12) reads very differently over #000 than over paper.
    for (const surface of SURFACE_ROLES) {
      const ratio = contrastBetween(palette["--mm-border"], palette[surface]);
      expect(ratio, `--mm-border on ${surface}`).toBeGreaterThan(1.1);
    }
  });

  it("surfaces step away from the page background", () => {
    // Elevation has to be perceivable, or every panel melts into the page.
    const surface = contrastBetween(palette["--mm-surface"], palette["--mm-bg"]);
    const elevated = contrastBetween(palette["--mm-elevated"], palette["--mm-bg"]);
    expect(surface).toBeGreaterThan(1.02);
    expect(elevated).toBeGreaterThan(surface);
  });

  it("hero heading text is legible at both ends of its gradient", () => {
    // `.hero-heading` is clipped-gradient text; both stops have to read against
    // the page. Display-sized, so the large-text threshold applies.
    for (const role of ["--mm-hero-from", "--mm-hero-to"] as const) {
      const ratio = contrastBetween(palette[role], palette["--mm-bg"]);
      expect(ratio, `${role} on --mm-bg`).toBeGreaterThanOrEqual(WCAG_AA_LARGE_TEXT);
    }
  });
});

describe("muted text with an opacity modifier", () => {
  /**
   * `text-muted/70` and friends compile to
   * `color-mix(in oklab, var(--color-muted) 70%, transparent)`, so the reader
   * sees the muted colour flattened over whatever is behind it. At 70% on the
   * dark theme that is 4.4:1 — a real AA failure that reads as "fine" because
   * the token it derives from passes.
   *
   * This test does not demand that every opacity step passes; it pins the
   * threshold below which the modifier must not be used for text, so the
   * finding stays discoverable instead of being rediscovered.
   */
  const dark = paletteFor("dark");

  it("passes at full strength", () => {
    expect(contrastBetween(dark["--mm-muted"], dark["--mm-bg"])).toBeGreaterThanOrEqual(
      WCAG_AA_NORMAL_TEXT,
    );
  });

  it.each([
    [0.8, true],
    [0.7, false],
    [0.6, false],
    [0.4, false],
  ])("at %s opacity, usable for body text: %s", (opacity, expected) => {
    const muted = dark["--mm-muted"];
    const faded = `${muted}${Math.round(opacity * 255)
      .toString(16)
      .padStart(2, "0")}`;
    const ratio = contrastBetween(faded, dark["--mm-bg"]);
    expect(ratio >= WCAG_AA_NORMAL_TEXT).toBe(expected);
  });
});
