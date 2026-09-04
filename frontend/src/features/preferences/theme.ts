/**
 * Site themes: the value of `<html data-theme="…">`.
 *
 * The palettes themselves live in CSS — the four hand-written ones in
 * `src/app/globals.css`, the generated ones in `src/app/themes.generated.css` —
 * as one block of `--mm-*` role variables each. This module owns only the
 * *identity* of a theme (which ones exist, what they are called, how a stored
 * string resolves to one), so the selection logic is testable without a DOM.
 *
 * ### Two kinds of theme, one list
 *
 * **Built-in**: Eclipse, Midnight, Sepia and Daylight. The app's own look,
 * hand-tuned, amber-accented, and unchanged — Eclipse in particular is
 * byte-identical to what shipped before any of this existed and is still the
 * default.
 *
 * **Generated**: base16 schemes from `tinted-theming/schemes`, mapped onto the
 * same role set by `scripts/themes/map.mjs` and gated at WCAG AA. These are the
 * ricing library: one scheme definition repaints the entire interface, the way
 * base16 repaints a terminal, an editor and a window manager from a single
 * palette. They are data, not code — see `scripts/themes/` to add or regenerate.
 *
 * The distinction matters to exactly two things: the default (always Eclipse)
 * and the credit line on a tile (community schemes are somebody's work). Every
 * other consumer treats the list as flat.
 */

import { GENERATED_THEMES } from "./themes.generated";
import type { GeneratedThemeMeta, ThemeScheme, ThemeSwatch } from "./theme-types";

/**
 * The hand-written palettes, in the order the picker shows them: the default
 * first, then its true-black sibling, then the two paper themes.
 */
export const BUILT_IN_THEMES = ["dark", "midnight", "sepia", "light"] as const;

export type BuiltInTheme = (typeof BUILT_IN_THEMES)[number];
export type GeneratedTheme = (typeof GENERATED_THEMES)[number]["id"];
export type ReadingTheme = BuiltInTheme | GeneratedTheme;

/** What the app has always looked like, and what an unset preference means. */
export const DEFAULT_READING_THEME: ReadingTheme = "dark";

/**
 * The unscoped half of the localStorage key the choice is stored under;
 * `scoped-storage` appends the `(user, profile)` namespace.
 *
 * Declared here rather than in `theme-store.ts` because the boot script in
 * `appearance-boot.tsx` has to find the same key before any store exists, and a
 * string that two files spell independently is a string that will one day be
 * spelled differently.
 */
export const READING_THEME_STORAGE_BASE = "manhwamaniacs:reading-theme";

export interface ReadingThemeMeta {
  id: ReadingTheme;
  label: string;
  /** One line for the settings tile and the command palette subtitle. */
  description: string;
  /** Whether the palette is dark- or light-based. */
  scheme: ThemeScheme;
  /**
   * Upstream credit for a generated scheme; absent on the app's own four.
   * Doubles as the "is this one of ours" flag — nothing else needs to care.
   */
  author?: string;
  /**
   * The colours the tile paints. Duplicated from the CSS on purpose: a swatch
   * has to show a palette that is NOT currently applied, so it cannot read the
   * live custom properties.
   */
  swatch: ThemeSwatch;
}

const BUILT_IN_META: Record<BuiltInTheme, ReadingThemeMeta> = {
  dark: {
    id: "dark",
    label: "Eclipse",
    description: "The original warm near-black.",
    scheme: "dark",
    swatch: {
      bg: "#0A0A0A",
      surface: "#181818",
      fg: "#DDE4EA",
      muted: "#9AA8B4",
      accent: "#F59E0B",
    },
  },
  midnight: {
    id: "midnight",
    label: "Midnight",
    description: "True black — saves power on OLED screens.",
    scheme: "dark",
    swatch: {
      bg: "#000000",
      surface: "#101010",
      fg: "#E7EDF3",
      muted: "#A6B3BF",
      accent: "#F59E0B",
    },
  },
  sepia: {
    id: "sepia",
    label: "Sepia",
    description: "Warm paper for long reading sessions.",
    scheme: "light",
    swatch: {
      bg: "#E8DCC6",
      surface: "#F7F0E2",
      fg: "#2B2318",
      muted: "#635340",
      accent: "#92400E",
    },
  },
  light: {
    id: "light",
    label: "Daylight",
    description: "Neutral light, for bright rooms.",
    scheme: "light",
    swatch: {
      bg: "#EFEDE9",
      surface: "#FCFBF9",
      fg: "#1A1917",
      muted: "#5A5751",
      accent: "#92400E",
    },
  },
};

function fromGenerated(meta: GeneratedThemeMeta): ReadingThemeMeta {
  return {
    id: meta.id as ReadingTheme,
    label: meta.label,
    description: meta.description,
    scheme: meta.scheme,
    author: meta.author,
    swatch: meta.swatch,
  };
}

/** Every theme, built-ins first. Order is the picker's order. */
export const READING_THEMES: readonly ReadingTheme[] = [
  ...BUILT_IN_THEMES,
  ...GENERATED_THEMES.map((meta) => meta.id as ReadingTheme),
];

export const READING_THEME_META: Record<ReadingTheme, ReadingThemeMeta> = {
  ...BUILT_IN_META,
  ...Object.fromEntries(
    GENERATED_THEMES.map((meta) => [meta.id, fromGenerated(meta)]),
  ),
} as Record<ReadingTheme, ReadingThemeMeta>;

/**
 * Membership as a set, not a linear scan: this is called on every snapshot read
 * of the theme store, and the list is now forty-odd long rather than four.
 */
const THEME_IDS = new Set<string>(READING_THEMES);

export function isReadingTheme(value: unknown): value is ReadingTheme {
  return typeof value === "string" && THEME_IDS.has(value);
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

/** The themes of one variant, in declared order — how the picker groups them. */
export function themesByScheme(scheme: ThemeScheme): readonly ReadingThemeMeta[] {
  return READING_THEMES.map((id) => READING_THEME_META[id]).filter(
    (meta) => meta.scheme === scheme,
  );
}

/**
 * Whether `meta` matches a free-text query.
 *
 * Matches the label, the blurb and the author, so "gruv", "paper" and "ibm" all
 * find something. Forty tiles is past the point where scrolling is the only
 * affordance a picker needs.
 */
export function themeMatches(meta: ReadingThemeMeta, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle === "") return true;
  return [meta.label, meta.description, meta.author ?? "", meta.id]
    .join(" ")
    .toLowerCase()
    .includes(needle);
}
