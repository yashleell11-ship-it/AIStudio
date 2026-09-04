import { describe, expect, it } from "vitest";
import {
  BASE_ROLES,
  paletteFor,
  roleBlock,
  ruleBody,
} from "./theme-css.testkit";
import {
  BUILT_IN_THEMES,
  DEFAULT_READING_THEME,
  READING_THEMES,
  READING_THEME_META,
  initialReadingTheme,
  isReadingTheme,
  parseReadingTheme,
  themeMatches,
  themesByScheme,
} from "./theme";

describe("reading theme identity", () => {
  it("describes every declared theme", () => {
    for (const theme of READING_THEMES) {
      const meta = READING_THEME_META[theme];
      expect(meta.id).toBe(theme);
      expect(meta.label).toBeTruthy();
      expect(meta.description).toBeTruthy();
      for (const role of ["bg", "surface", "fg", "muted", "accent"] as const) {
        expect(meta.swatch[role], `${theme}.${role}`).toMatch(/^#[0-9a-f]{6}$/i);
      }
    }
  });

  it("gives every theme a unique id and a unique label", () => {
    // Two tiles reading "Gruvbox" would be a coin flip for the viewer, and two
    // ids would silently drop a palette out of the record.
    expect(new Set(READING_THEMES).size).toBe(READING_THEMES.length);
    const labels = READING_THEMES.map((id) => READING_THEME_META[id].label);
    expect(new Set(labels).size).toBe(labels.length);
  });

  it("credits every generated palette and none of the built-in four", () => {
    for (const theme of READING_THEMES) {
      const meta = READING_THEME_META[theme];
      const isBuiltIn = (BUILT_IN_THEMES as readonly string[]).includes(theme);
      if (isBuiltIn) expect(meta.author, theme).toBeUndefined();
      else expect(meta.author, theme).toBeTruthy();
    }
  });

  it("ships a library worth calling one — dark and light both well stocked", () => {
    expect(themesByScheme("dark").length).toBeGreaterThanOrEqual(20);
    expect(themesByScheme("light").length).toBeGreaterThanOrEqual(10);
    expect(themesByScheme("dark").length + themesByScheme("light").length).toBe(
      READING_THEMES.length,
    );
  });

  it("keeps the existing dark palette as the default", () => {
    expect(DEFAULT_READING_THEME).toBe("dark");
    expect(READING_THEMES[0]).toBe("dark");
  });

  it("ships one true-black, one sepia and one light variant", () => {
    expect(READING_THEME_META.midnight.swatch.bg).toBe("#000000");
    expect(READING_THEME_META.sepia.scheme).toBe("light");
    expect(READING_THEME_META.light.scheme).toBe("light");
  });

  it("keeps an amber/rose accent in the app's own four (Eclipse Warm survives)", () => {
    // Hue of the accent must stay in the warm 20°–45° band; only its lightness
    // moves, so paper themes can clear contrast without changing the identity.
    // The generated palettes are exempt by design — a Nord that had been
    // repainted amber would not be Nord, and the whole point of the library is
    // that each scheme keeps its own accent family.
    for (const theme of BUILT_IN_THEMES) {
      const hue = hueOf(READING_THEME_META[theme].swatch.accent);
      expect(hue).toBeGreaterThanOrEqual(20);
      expect(hue).toBeLessThanOrEqual(45);
    }
  });
});

describe("parseReadingTheme", () => {
  it("accepts every declared theme", () => {
    for (const theme of READING_THEMES) {
      expect(parseReadingTheme(theme)).toBe(theme);
    }
  });

  it("tolerates surrounding whitespace", () => {
    expect(parseReadingTheme("  sepia \n")).toBe("sepia");
  });

  it("reports an absent or unrecognised value as unset", () => {
    expect(parseReadingTheme(null)).toBeNull();
    expect(parseReadingTheme("")).toBeNull();
    // Solarized is in the corpus and fails the contrast gate, so it is exactly
    // the kind of id someone might expect to work and which must not.
    expect(parseReadingTheme("solarized-dark")).toBeNull();
    expect(parseReadingTheme("DARK")).toBeNull();
  });
});

describe("isReadingTheme", () => {
  it("narrows only exact theme ids", () => {
    expect(isReadingTheme("midnight")).toBe(true);
    expect(isReadingTheme("oled")).toBe(false);
    expect(isReadingTheme(null)).toBe(false);
    expect(isReadingTheme(3)).toBe(false);
  });
});

describe("initialReadingTheme", () => {
  it("honours a stored choice over the OS preference", () => {
    expect(initialReadingTheme("sepia", true)).toBe("sepia");
    expect(initialReadingTheme("midnight", true)).toBe("midnight");
    // The point of "initial value only": choosing dark on a light-preferring
    // machine must stick.
    expect(initialReadingTheme("dark", true)).toBe("dark");
  });

  it("seeds a first visit from prefers-color-scheme", () => {
    expect(initialReadingTheme(null, true)).toBe("light");
    expect(initialReadingTheme(null, false)).toBe("dark");
  });

  it("treats an unrecognised stored value as unset", () => {
    expect(initialReadingTheme("solarized", true)).toBe("light");
    expect(initialReadingTheme("solarized", false)).toBe(DEFAULT_READING_THEME);
  });

  it("honours a generated palette the same as a built-in one", () => {
    expect(initialReadingTheme("nord", true)).toBe("nord");
    expect(initialReadingTheme("catppuccin-latte", false)).toBe("catppuccin-latte");
  });
});

describe("themeMatches", () => {
  const nord = READING_THEME_META.nord;

  it("matches an empty query, so an unfiltered picker shows everything", () => {
    expect(themeMatches(nord, "")).toBe(true);
    expect(themeMatches(nord, "   ")).toBe(true);
  });

  it("matches on label, id, blurb and author", () => {
    expect(themeMatches(nord, "nord")).toBe(true);
    expect(themeMatches(nord, "NORD")).toBe(true);
    expect(themeMatches(nord, "arctic")).toBe(true);
    expect(themeMatches(nord, "arcticicestudio")).toBe(true);
    expect(themeMatches(nord, "gruvbox")).toBe(false);
  });

  it("finds a family by prefix", () => {
    const hits = READING_THEMES.map((id) => READING_THEME_META[id]).filter((meta) =>
      themeMatches(meta, "gruv"),
    );
    expect(hits.length).toBeGreaterThanOrEqual(3);
  });
});

/**
 * The palettes as CSS: what the browser will actually load.
 *
 * globals.css states the light palette twice — once for `[data-theme="light"]`
 * and once for the `prefers-color-scheme` first-paint fallback, which cannot
 * share a selector with it. CSS has no way to keep the two in step, so this
 * does. And every generated palette has to be a COMPLETE role set, because it
 * cascades over the dark defaults: one role left out is a Catppuccin Latte with
 * a near-black scrollbar.
 */
describe("theme CSS blocks", () => {
  it("declares a block for every theme the app offers", () => {
    // The picker and the stylesheets are generated from different files. If
    // they ever disagree, a tile applies an id no rule matches and the viewer
    // silently gets Eclipse instead of what they clicked.
    for (const theme of READING_THEMES) {
      if (theme === DEFAULT_READING_THEME) continue;
      expect(() => roleBlock(`:root[data-theme="${theme}"]`), theme).not.toThrow();
    }
  });

  it("restates the surface and text roles in every non-default theme", () => {
    // A theme that inherited any of these from the dark base would render as a
    // half-applied palette (light panels, near-white text), so each one has to
    // be stated explicitly rather than left to the cascade.
    const required = [
      "--mm-bg",
      "--mm-surface",
      "--mm-elevated",
      "--mm-fg",
      "--mm-muted",
      "--mm-border",
    ];
    for (const theme of READING_THEMES) {
      if (theme === DEFAULT_READING_THEME) continue;
      const roles = roleBlock(`:root[data-theme="${theme}"]`);
      for (const role of required) {
        expect(roles, `${theme} does not set ${role}`).toHaveProperty(role);
      }
    }
  });

  it("keeps the light theme and the prefers-color-scheme fallback identical", () => {
    expect(roleBlock(":root:not([data-theme])")).toEqual(
      roleBlock(':root[data-theme="light"]'),
    );
  });

  it("restates every role the dark base defines, and invents none", () => {
    const base = Object.keys(BASE_ROLES);
    expect(base.length).toBeGreaterThan(10);
    for (const theme of READING_THEMES) {
      if (theme === DEFAULT_READING_THEME) continue;
      const overrides = Object.keys(roleBlock(`:root[data-theme="${theme}"]`));
      // Every override must name a role the base declares; a typo'd role would
      // otherwise be a variable nothing reads.
      for (const role of overrides) {
        expect(base, `${theme} sets unknown role ${role}`).toContain(role);
      }
      // And a generated palette must be complete, since it has no sibling to
      // inherit the rest from.
      if (!(BUILT_IN_THEMES as readonly string[]).includes(theme)) {
        expect(overrides.length, `${theme} is missing roles`).toBe(base.length);
      }
    }
  });

  it("sets a color-scheme on every theme so form controls follow it", () => {
    for (const theme of READING_THEMES) {
      const body = ruleBody(`:root[data-theme="${theme}"]`);
      expect(body, theme).toContain(
        `color-scheme: ${READING_THEME_META[theme].scheme}`,
      );
    }
  });

  it("agrees with the swatch the picker paints", () => {
    // The tile shows a palette that is not applied, so it cannot read the live
    // variables — it carries its own copy. This is what stops the two drifting.
    for (const theme of READING_THEMES) {
      const roles = paletteFor(theme);
      const { swatch } = READING_THEME_META[theme];
      expect(roles["--mm-bg"].toUpperCase(), `${theme} bg`).toBe(
        swatch.bg.toUpperCase(),
      );
      expect(roles["--mm-elevated"].toUpperCase(), `${theme} surface`).toBe(
        swatch.surface.toUpperCase(),
      );
      expect(roles["--mm-fg"].toUpperCase(), `${theme} fg`).toBe(
        swatch.fg.toUpperCase(),
      );
      expect(roles["--mm-muted"].toUpperCase(), `${theme} muted`).toBe(
        swatch.muted.toUpperCase(),
      );
      expect(roles["--mm-primary"].toUpperCase(), `${theme} accent`).toBe(
        swatch.accent.toUpperCase(),
      );
    }
  });

  it("leaves the cover-art scrim tokens out of every theme", () => {
    // `--color-void` / `--color-panel` scrim over artwork with white text on
    // top; a theme that lightened them would make that text unreadable.
    for (const theme of READING_THEMES) {
      const body = ruleBody(`:root[data-theme="${theme}"]`);
      expect(body, theme).not.toContain("--color-void");
      expect(body, theme).not.toContain("--color-panel");
    }
  });
});

/** Hue in degrees, 0–360, of a `#rrggbb` colour. */
function hueOf(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const delta = max - min;
  if (delta === 0) return 0;
  let hue: number;
  if (max === r) hue = ((g - b) / delta) % 6;
  else if (max === g) hue = (b - r) / delta + 2;
  else hue = (r - g) / delta + 4;
  hue *= 60;
  return hue < 0 ? hue + 360 : hue;
}
