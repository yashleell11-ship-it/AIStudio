/**
 * Reading themes: the value of `<html data-theme="…">`.
 *
 * The palettes themselves live in `src/app/globals.css` — one block of
 * `--mm-*` role variables per theme. This module owns only the *identity* of a
 * theme (which ones exist, what they are called, how a stored string resolves
 * to one), so the selection logic is testable without a DOM.
 *
 * Eclipse Warm is not replaced by any of these. Amber/rose stay the accent
 * family in all four; the paper themes deepen amber to burnt amber so accent
 * text still clears WCAG AA against a light background.
 */

export const READING_THEMES = ["dark", "midnight", "sepia", "light"] as const;

export type ReadingTheme = (typeof READING_THEMES)[number];

/** What the app has always looked like, and what an unset preference means. */
export const DEFAULT_READING_THEME: ReadingTheme = "dark";

export interface ReadingThemeMeta {
  id: ReadingTheme;
  label: string;
  /** One line for the settings list and the command palette subtitle. */
  description: string;
  /** Whether the palette is dark- or light-based. */
  scheme: "dark" | "light";
  /**
   * Two hexes for the preview chip: page background and its primary text.
   * Duplicated from the CSS on purpose — a swatch has to paint the colour of a
   * theme that is NOT currently applied, so it cannot read the live variables.
   */
  swatch: { bg: string; fg: string; accent: string };
}

export const READING_THEME_META: Record<ReadingTheme, ReadingThemeMeta> = {
  dark: {
    id: "dark",
    label: "Eclipse",
    description: "The original warm near-black.",
    scheme: "dark",
    swatch: { bg: "#0A0A0A", fg: "#DDE4EA", accent: "#F59E0B" },
  },
  midnight: {
    id: "midnight",
    label: "Midnight",
    description: "True black — saves power on OLED screens.",
    scheme: "dark",
    swatch: { bg: "#000000", fg: "#E7EDF3", accent: "#F59E0B" },
  },
  sepia: {
    id: "sepia",
    label: "Sepia",
    description: "Warm paper for long reading sessions.",
    scheme: "light",
    swatch: { bg: "#E8DCC6", fg: "#2B2318", accent: "#92400E" },
  },
  light: {
    id: "light",
    label: "Daylight",
    description: "Neutral light, for bright rooms.",
    scheme: "light",
    swatch: { bg: "#EFEDE9", fg: "#1A1917", accent: "#92400E" },
  },
};

export function isReadingTheme(value: unknown): value is ReadingTheme {
  return (
    typeof value === "string" &&
    (READING_THEMES as readonly string[]).includes(value)
  );
}

/**
 * A stored preference, or `null` when there is none to honour — an unknown or
 * absent value is "unset", never a silent fallback to the default, because the
 * caller distinguishes the two (see {@link initialReadingTheme}).
 */
export function parseReadingTheme(raw: string | null): ReadingTheme | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  return isReadingTheme(trimmed) ? trimmed : null;
}

/**
 * The theme to show right now.
 *
 * `prefersLight` is consulted ONLY when nothing is stored. That is the whole
 * contract: the OS preference seeds a first visit, and from then on an explicit
 * choice wins — a viewer who picked Sepia does not get flipped back to dark
 * every sunset.
 */
export function initialReadingTheme(
  stored: string | null,
  prefersLight: boolean,
): ReadingTheme {
  const parsed = parseReadingTheme(stored);
  if (parsed !== null) return parsed;
  return prefersLight ? "light" : DEFAULT_READING_THEME;
}

/** The next theme in the declared order — what the palette's toggle action runs. */
export function nextReadingTheme(current: ReadingTheme): ReadingTheme {
  const index = READING_THEMES.indexOf(current);
  return READING_THEMES[(index + 1) % READING_THEMES.length];
}
