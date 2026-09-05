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
 * hand-tuned and amber-accented. Eclipse is byte-identical to what shipped
 * before any of this existed; it is simply no longer the default.
 *
 * **Generated**: base16 schemes from `tinted-theming/schemes`, mapped onto the
 * same role set by `scripts/themes/map.mjs` and gated at WCAG AA. These are the
 * ricing library: one scheme definition repaints the entire interface, the way
 * base16 repaints a terminal, an editor and a window manager from a single
 * palette. They are data, not code — see `scripts/themes/` to add or regenerate.
 *
 * The distinction matters to exactly one thing now: the credit line on a tile
 * (community schemes are somebody's work). Every other consumer treats the list
 * as flat — including the default, which is a generated palette.
 */

import { GENERATED_THEMES } from "./themes.generated";
import type { GeneratedThemeMeta, ThemeScheme, ThemeSwatch } from "./theme-types";

/**
 * The hand-written palettes, in the order the picker shows them: the app's
 * original look, then its true-black sibling, then the two paper themes.
 */
export const BUILT_IN_THEMES = ["dark", "midnight", "sepia", "light"] as const;

export type BuiltInTheme = (typeof BUILT_IN_THEMES)[number];
export type GeneratedTheme = (typeof GENERATED_THEMES)[number]["id"];
export type ReadingTheme = BuiltInTheme | GeneratedTheme;

/**
 * What an unset preference means, and what the app looks like out of the box.
 *
 * GitHub Dark: near-black, low-chroma, blue-grey — the look the app is asked to
 * have by default. It is not just the seed for a new profile; it is the ONLY
 * palette the pre-auth screens can paint, because `data-theme` comes from a
 * per-(user, profile) key that does not exist before sign-in and the boot
 * script declines on /login and /register by design.
 *
 * Whatever this names must also be the bare `:root` role block in globals.css.
 * Nothing enforces that at runtime — the browser reads the CSS and this module
 * never does — so `theme.test.ts` compares the two and fails on a drift. Change
 * one and you must change the other, or the app paints one palette before
 * hydration and a different one after.
 */
export const DEFAULT_READING_THEME: ReadingTheme = "github-dark";

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
 * The theme to show right now: the stored choice, or the default.
 *
 * There is deliberately no third input. This used to take a `prefersLight` flag
 * and seed a first visit with Daylight on a light-mode OS, mirrored by a
 * `prefers-color-scheme` block in globals.css. Both are gone: the app has a
 * named default now, and a default that changed colour with the viewer's OS
 * would mean the sign-in page — which can never read a stored choice, and so
 * only ever paints the default — was white on one phone and near-black on
 * another.
 *
 * A stored choice still wins over everything, which is the part that always
 * mattered: a viewer who picked Sepia keeps Sepia, and every light palette is
 * one click away in the picker.
 */
export function initialReadingTheme(stored: string | null): ReadingTheme {
  return parseReadingTheme(stored) ?? DEFAULT_READING_THEME;
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
