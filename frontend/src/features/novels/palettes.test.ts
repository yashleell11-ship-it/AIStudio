import { describe, expect, it } from "vitest";
import { contrastBetween } from "@/lib/contrast";
import {
  DEFAULT_DARK_PALETTE,
  DEFAULT_LIGHT_PALETTE,
  isNovelPaletteChoice,
  isNovelPaletteId,
  NOVEL_PALETTES,
  novelPalette,
  paletteSurface,
  palettesByScheme,
  resolvePalette,
  resolvePaletteChoice,
  SITE_PALETTE,
} from "./palettes";

/**
 * The floor for long-form body text. Higher than WCAG AA's 4.5:1 on purpose:
 * a reader's eyes are on these two colours for an hour at a stretch, which is
 * a different problem from reading a button label once.
 */
const INK_MIN_CONTRAST = 6;
/** Secondary text (chapter meta, dividers) — WCAG's large-text/non-text bar. */
const MUTED_MIN_CONTRAST = 3;

describe("novel palette contrast", () => {
  it.each(NOVEL_PALETTES.map((palette) => [palette.label, palette] as const))(
    "%s keeps body ink at or above 6:1 against its page",
    (_label, palette) => {
      expect(contrastBetween(palette.ink, palette.bg)).toBeGreaterThanOrEqual(
        INK_MIN_CONTRAST,
      );
    },
  );

  it.each(NOVEL_PALETTES.map((palette) => [palette.label, palette] as const))(
    "%s keeps muted text at or above 3:1 against its page",
    (_label, palette) => {
      expect(contrastBetween(palette.muted, palette.bg)).toBeGreaterThanOrEqual(
        MUTED_MIN_CONTRAST,
      );
    },
  );

  it("never pairs pure white ink with a pure black page (halation)", () => {
    const black = novelPalette("black");
    expect(black.bg).toBe("#000000");
    expect(black.ink.toUpperCase()).not.toBe("#FFFFFF");
    // The rule is about maximum contrast, not about the literal hex: anything
    // at 21:1 is white-on-black however it is spelled.
    expect(contrastBetween(black.ink, black.bg)).toBeLessThan(21);
  });

  it("keeps dark-surface ink dimmer than white, deliberately", () => {
    for (const palette of palettesByScheme("dark")) {
      expect(contrastBetween(palette.ink, palette.bg)).toBeLessThan(16);
    }
  });

  it("ranks ink ahead of muted on every surface", () => {
    for (const palette of NOVEL_PALETTES) {
      expect(contrastBetween(palette.ink, palette.bg)).toBeGreaterThan(
        contrastBetween(palette.muted, palette.bg),
      );
    }
  });
});

describe("novel palette catalogue", () => {
  it("ships twelve surfaces with unique ids", () => {
    expect(NOVEL_PALETTES).toHaveLength(12);
    expect(new Set(NOVEL_PALETTES.map((p) => p.id)).size).toBe(12);
  });

  it("splits six light surfaces from six dark ones", () => {
    expect(palettesByScheme("light")).toHaveLength(6);
    expect(palettesByScheme("dark")).toHaveLength(6);
  });

  it("declares every colour as a parseable hex", () => {
    for (const palette of NOVEL_PALETTES) {
      for (const colour of [palette.bg, palette.ink, palette.muted]) {
        expect(colour).toMatch(/^#[0-9A-F]{6}$/);
      }
    }
  });
});

describe("resolvePaletteChoice", () => {
  it("seeds Paper in a light app and Dusk in a dark one when nothing is stored", () => {
    expect(resolvePaletteChoice(null, "light")).toBe(DEFAULT_LIGHT_PALETTE);
    expect(resolvePaletteChoice(null, "dark")).toBe(DEFAULT_DARK_PALETTE);
    expect(resolvePaletteChoice(undefined, "light")).toBe("paper");
    expect(resolvePaletteChoice("not-a-palette", "dark")).toBe("dusk");
  });

  it("keeps a light surface while the app is dark — the palette is independent", () => {
    expect(resolvePaletteChoice("sepia", "dark")).toBe("sepia");
    expect(resolvePaletteChoice("midnight", "light")).toBe("midnight");
  });

  it("honours Follow site theme as an explicit choice", () => {
    expect(resolvePaletteChoice(SITE_PALETTE, "dark")).toBe(SITE_PALETTE);
    expect(resolvePalette(SITE_PALETTE)).toBeNull();
  });
});

describe("palette guards", () => {
  it("accepts known ids and rejects everything else", () => {
    expect(isNovelPaletteId("rose-pine")).toBe(true);
    expect(isNovelPaletteId("site")).toBe(false);
    expect(isNovelPaletteId(7)).toBe(false);
    expect(isNovelPaletteChoice("site")).toBe(true);
    expect(isNovelPaletteChoice("rose-pine")).toBe(true);
    expect(isNovelPaletteChoice("hot-pink")).toBe(false);
  });

  it("resolves a concrete surface for every non-site choice", () => {
    for (const palette of NOVEL_PALETTES) {
      expect(resolvePalette(palette.id)).toEqual(palette);
    }
  });
});

describe("paletteSurface", () => {
  it("resolves a chosen palette to its own colours", () => {
    const surface = paletteSurface(novelPalette("paper"));
    expect(surface.bg).toBe("#F5F1E8");
    expect(surface.ink).toBe("#2A2622");
    expect(surface.muted).toBe("#8A7F6D");
    expect(surface.rule).toContain("#8A7F6D");
  });

  it("resolves 'Follow site theme' to the app's own tokens, not to a palette", () => {
    const surface = paletteSurface(null);
    expect(surface.bg).toBe("var(--color-bg)");
    expect(surface.ink).toBe("var(--color-fg)");
    expect(surface.muted).toBe("var(--color-muted)");
    // One rendering path: the inherit case is still an inline colour, so the
    // reader never swaps between inline styles and utility classes.
    expect(surface.rule).toContain("var(--color-muted)");
  });

  it("paints every palette, so none can render a missing colour", () => {
    for (const palette of NOVEL_PALETTES) {
      const surface = paletteSurface(palette);
      for (const value of Object.values(surface)) {
        expect(value, palette.id).toBeTruthy();
      }
    }
  });
});
