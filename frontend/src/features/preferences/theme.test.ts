import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_READING_THEME,
  READING_THEMES,
  READING_THEME_META,
  initialReadingTheme,
  isReadingTheme,
  nextReadingTheme,
  parseReadingTheme,
  type ReadingTheme,
} from "./theme";

describe("reading theme identity", () => {
  it("describes every declared theme", () => {
    for (const theme of READING_THEMES) {
      const meta = READING_THEME_META[theme];
      expect(meta.id).toBe(theme);
      expect(meta.label).toBeTruthy();
      expect(meta.description).toBeTruthy();
      expect(meta.swatch.bg).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.swatch.fg).toMatch(/^#[0-9a-f]{6}$/i);
      expect(meta.swatch.accent).toMatch(/^#[0-9a-f]{6}$/i);
    }
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

  it("keeps an amber/rose accent in every theme (Eclipse Warm survives)", () => {
    // Hue of the accent must stay in the warm 20°–45° band; only its lightness
    // moves, so paper themes can clear contrast without changing the identity.
    for (const theme of READING_THEMES) {
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
    expect(parseReadingTheme("solarized")).toBeNull();
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
});

describe("nextReadingTheme", () => {
  it("cycles through every theme and returns to the start", () => {
    let theme: ReadingTheme = READING_THEMES[0];
    const seen: ReadingTheme[] = [theme];
    for (let i = 0; i < READING_THEMES.length - 1; i += 1) {
      theme = nextReadingTheme(theme);
      seen.push(theme);
    }
    expect(new Set(seen).size).toBe(READING_THEMES.length);
    expect(nextReadingTheme(theme)).toBe(READING_THEMES[0]);
  });
});

/**
 * globals.css states the light palette twice — once for `[data-theme="light"]`
 * and once for the `prefers-color-scheme` first-paint fallback, which cannot
 * share a selector with it. CSS has no way to keep the two in step, so this
 * does: edit one and forget the other and the build fails here rather than in
 * front of a viewer who sees half a theme for 200ms.
 */
describe("globals.css theme blocks", () => {
  const css = readFileSync(
    path.resolve(__dirname, "../../app/globals.css"),
    "utf8",
  );

  /** The `--mm-*` declarations of the rule whose selector line matches. */
  function roleBlock(selector: string): Record<string, string> {
    const start = css.indexOf(selector);
    expect(start, `selector not found: ${selector}`).toBeGreaterThanOrEqual(0);
    const open = css.indexOf("{", start);
    const end = css.indexOf("}", open);
    const body = css.slice(open + 1, end);
    const roles: Record<string, string> = {};
    for (const line of body.split(";")) {
      const match = /(--mm-[a-z0-9-]+)\s*:\s*([^;]+)/i.exec(line);
      if (match) roles[match[1]] = match[2].trim();
    }
    return roles;
  }

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

  it("restates every role the dark base defines", () => {
    const base = Object.keys(roleBlock(":root {"));
    expect(base.length).toBeGreaterThan(10);
    for (const theme of ["midnight", "sepia", "light"] as const) {
      const overrides = Object.keys(roleBlock(`:root[data-theme="${theme}"]`));
      // Every override must name a role the base declares; a typo'd role would
      // otherwise be a variable nothing reads.
      for (const role of overrides) {
        expect(base, `${theme} sets unknown role ${role}`).toContain(role);
      }
    }
  });

  it("leaves the cover-art scrim tokens out of every theme", () => {
    // `--color-void` / `--color-panel` scrim over artwork with white text on
    // top; a theme that lightened them would make that text unreadable.
    for (const theme of READING_THEMES) {
      const start = css.indexOf(`:root[data-theme="${theme}"]`);
      if (start < 0) continue;
      const body = css.slice(start, css.indexOf("}", start));
      expect(body).not.toContain("--color-void");
      expect(body).not.toContain("--color-panel");
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
