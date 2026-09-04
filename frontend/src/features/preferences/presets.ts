/**
 * Design presets: the value of `<html data-preset="…">`.
 *
 * The sibling of `theme.ts`, and deliberately built the same way. A THEME
 * answers "what colour is this app" — forty-two palettes, one attribute, all
 * of it data. A PRESET answers "what SHAPE is it": density, surface treatment,
 * corner radius, type scale, how a library is laid out, how much furniture the
 * reader shows.
 *
 * The two axes are orthogonal and both persist per profile. Nord + Compact and
 * Nord + Editorial are both real choices, and neither had to be authored: a
 * preset never names a colour and a theme never names a length, so the 5 × 42
 * grid is filled in by the cascade rather than by hand. `presets.css` carries
 * the token bundles; this module owns only the *identity* of a preset (which
 * ones exist, what they are called, how a stored string resolves to one) plus
 * the handful of decisions that are not expressible as CSS custom properties
 * at all — the library layout a preset opens with, whether the reader starts
 * in cinema mode, and how much the JS-driven motion primitives should move.
 *
 * ### Why Signature and not Eclipse
 *
 * The design brief called the default preset "Eclipse". That is already the
 * label of the default THEME, and the two pickers sit on the same settings
 * screen — a viewer reading "Eclipse" twice, once under Design and once under
 * Appearance, learns nothing from either. `Signature` says what it is: the
 * app's own look, the one the owner uses daily, and the one every other preset
 * is a departure from. The regression bar it names is unchanged and is
 * asserted in `preset.test.ts`.
 */

import type { LibraryDensity } from "@/features/library/density";

/** Every preset, in the order the picker shows them: the default first. */
export const DESIGN_PRESETS = [
  "signature",
  "flat",
  "compact",
  "editorial",
  "cinema",
] as const;

export type DesignPreset = (typeof DESIGN_PRESETS)[number];

/** What the app has always looked like, and what an unset preference means. */
export const DEFAULT_DESIGN_PRESET: DesignPreset = "signature";

/**
 * The unscoped half of the localStorage key the choice is stored under;
 * `scoped-storage` appends the `(user, profile)` namespace.
 *
 * Declared here rather than in `preset-store.ts` for the same reason the theme
 * key is: the boot script in `preset-boot.tsx` has to find this key before any
 * store exists, and a string two files spell independently is a string that
 * will one day be spelled differently.
 */
export const DESIGN_PRESET_STORAGE_BASE = "manhwamaniacs:design-preset";

/**
 * The miniature a tile paints.
 *
 * Unlike a theme swatch, this carries no colours: a preset tile shows the
 * preset's shape wearing the palette that is actually applied, because that is
 * the honest preview — the viewer is choosing shape, and the colour they will
 * get is the colour already on screen. What it does have to carry is the
 * geometry, since the tile is showing a preset that is NOT applied and so
 * cannot read the live `--shape-*` values.
 */
export interface PresetPreview {
  /** Corner radius of the miniature's panels, in px. */
  radius: number;
  /** Gap between the miniature's elements, in px. */
  gap: number;
  /** Translucent surfaces (the fill is glass) rather than opaque ones. */
  translucent: boolean;
  /** Whether panels are drawn with a visible edge. */
  bordered: boolean;
  /** How many content rows the miniature packs — the density tell. */
  rows: number;
  /** Headings set in the book serif rather than the display sans. */
  serif: boolean;
}

export interface DesignPresetMeta {
  id: DesignPreset;
  label: string;
  /** One line for the settings tile and the command palette subtitle. */
  description: string;
  /** The single sentence that says what this preset is FOR. */
  character: string;
  preview: PresetPreview;
  /**
   * The library layout this preset opens with. Only a default: the density
   * control in the library toolbar still wins once a profile has used it, the
   * same way an explicitly chosen theme wins over the OS preference.
   */
  density: LibraryDensity;
  /**
   * Whether the reader starts with its chrome auto-hiding. Also only a
   * default — the reader's own cinema toggle still wins once used.
   */
  readerCinema: boolean;
  /**
   * Motion multiplier, 0 (instant) to 1 (as designed).
   *
   * Mirrors `--shape-motion` in `presets.css` for the motion primitives that
   * animate through React state and so cannot read a CSS variable.
   * `preset.test.ts` asserts the two numbers agree.
   */
  motion: number;
}

export const DESIGN_PRESET_META: Record<DesignPreset, DesignPresetMeta> = {
  signature: {
    id: "signature",
    label: "Signature",
    description: "Glass panels, generous spacing, poster-led browse.",
    character: "The app as designed. Unchanged, and the one everything else departs from.",
    preview: { radius: 6, gap: 5, translucent: true, bordered: true, rows: 2, serif: false },
    density: "comfortable",
    readerCinema: false,
    motion: 1,
  },
  flat: {
    id: "flat",
    label: "Flat",
    description: "Solid surfaces, crisp hairlines, no blur.",
    character: "The same app rendered as a tool rather than a showcase — and cheaper to paint.",
    preview: { radius: 3, gap: 5, translucent: false, bordered: true, rows: 2, serif: false },
    density: "comfortable",
    readerCinema: false,
    motion: 0.7,
  },
  compact: {
    id: "compact",
    label: "Compact",
    description: "Tighter rhythm, smaller type, many more covers per screen.",
    character: "For scanning a big library rather than browsing a small one.",
    preview: { radius: 4, gap: 3, translucent: true, bordered: true, rows: 4, serif: false },
    density: "compact",
    readerCinema: false,
    motion: 0.6,
  },
  editorial: {
    id: "editorial",
    label: "Editorial",
    description: "Serif headings, wide margins, metadata beside the artwork.",
    character: "Typography leads. Reads like a publication, not a shelf.",
    preview: { radius: 2, gap: 6, translucent: false, bordered: true, rows: 3, serif: true },
    density: "list",
    readerCinema: false,
    motion: 0.8,
  },
  cinema: {
    id: "cinema",
    label: "Cinema",
    description: "No frames, edge-to-edge, almost no motion.",
    character: "The chrome gets out of the way. For reading, not managing.",
    preview: { radius: 10, gap: 4, translucent: true, bordered: false, rows: 2, serif: false },
    density: "comfortable",
    readerCinema: true,
    motion: 0.35,
  },
};

const PRESET_IDS = new Set<string>(DESIGN_PRESETS);

export function isDesignPreset(value: unknown): value is DesignPreset {
  return typeof value === "string" && PRESET_IDS.has(value);
}

/**
 * A stored preference, or `null` when there is none to honour.
 *
 * An unknown or absent value is "unset", never a silent fallback — the caller
 * distinguishes the two, so the settings panel can say whether the viewer has
 * actually chosen or is simply seeing the default.
 */
export function parseDesignPreset(raw: string | null): DesignPreset | null {
  if (raw === null) return null;
  const trimmed = raw.trim();
  return isDesignPreset(trimmed) ? trimmed : null;
}

/**
 * The preset to apply right now.
 *
 * There is no OS preference to seed this from — nothing about a device says
 * "this person wants serif headings" — so an unset preference is simply the
 * default. That is the one place this differs from {@link
 * import("./theme").initialReadingTheme}.
 */
export function initialDesignPreset(stored: string | null): DesignPreset {
  return parseDesignPreset(stored) ?? DEFAULT_DESIGN_PRESET;
}

/** Every preset's metadata, in picker order. */
export function designPresetList(): readonly DesignPresetMeta[] {
  return DESIGN_PRESETS.map((id) => DESIGN_PRESET_META[id]);
}
