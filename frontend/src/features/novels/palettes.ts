/**
 * Reading-surface palettes for the novel reader.
 *
 * The page a novel is read on is NOT the app's theme. A reader wants warm paper
 * at midday and a dim slate at 2am regardless of what the rest of the app looks
 * like, and forcing the two to agree is exactly the thing every dedicated
 * reading app gets right and every "we already have a dark mode" app gets
 * wrong. So the palette is its own preference (see `settings.ts`), and
 * `"site"` — "Follow site theme" — is one option among thirteen, not the frame
 * the other twelve live inside.
 *
 * ### Rules these colours obey, deliberately
 *
 * - **No pure white on pure black.** Maximum-contrast text on an OLED-black
 *   page haloes ("halation") and is genuinely painful over an hour. `black`
 *   below is `#000000` with a dimmed bone ink, never `#FFFFFF`.
 * - **Dark ink is dimmer than white on purpose.** Every dark palette's `ink`
 *   sits well below 100% luminance. That is not an oversight to be "fixed".
 * - **Warm backgrounds get warm-dark ink**, never a neutral grey — neutral
 *   grey over cream reads as dirty rather than soft.
 *
 * ### Contrast floor
 *
 * `palettes.test.ts` asserts `ink` clears **6:1** and `muted` clears **3:1**
 * against `bg` by WCAG relative luminance, for every palette. A palette that
 * misses that is a bug, not a matter of taste — long-form body text is the one
 * place in the app where a reader's eyes are on the same two colours for an
 * hour at a time.
 *
 * Three of the approved colours missed that floor when measured, and are
 * shipped adjusted — each noted inline with the value it replaced, so the
 * change is visible rather than silently absorbed. Every adjustment keeps the
 * palette's hue and its family: two of them are literally the source theme's
 * own next step on the same ramp.
 */

export type NovelPaletteId =
  | "paper"
  | "sepia"
  | "solarized-light"
  | "soft-grey"
  | "cream"
  | "dawn"
  | "dusk"
  | "midnight"
  | "black"
  | "solarized-dark"
  | "forest"
  | "rose-pine";

/** Whether a palette is a light-on-dark or dark-on-light surface. */
export type PaletteScheme = "light" | "dark";

export interface NovelPalette {
  id: NovelPaletteId;
  label: string;
  scheme: PaletteScheme;
  /** Page background. */
  bg: string;
  /** Body text. */
  ink: string;
  /** Chapter meta, dividers, the furniture around the prose. */
  muted: string;
}

/**
 * The reader's palette choice: one of the twelve surfaces, or `"site"` for
 * "Follow site theme", which inherits the app's own `--mm-*` tokens instead of
 * painting a surface of its own.
 */
export const SITE_PALETTE = "site" as const;
export type NovelPaletteChoice = NovelPaletteId | typeof SITE_PALETTE;

export const NOVEL_PALETTES: readonly NovelPalette[] = [
  // --- light surfaces ---
  {
    id: "paper",
    label: "Paper",
    scheme: "light",
    bg: "#F5F1E8",
    ink: "#2A2622",
    muted: "#8A7F6D",
  },
  {
    id: "sepia",
    label: "Sepia",
    scheme: "light",
    bg: "#F4ECD8",
    ink: "#5B4636",
    muted: "#8A7250",
  },
  {
    id: "solarized-light",
    label: "Solarized light",
    scheme: "light",
    bg: "#FDF6E3",
    // Approved as #586E75 (Solarized `base01`), which measures 4.99:1 here —
    // under the 6:1 floor. Darkened along its own hue to 6.50:1; visually the
    // same slate-teal, a shade deeper.
    ink: "#4A5C62",
    // Approved as #93A1A1 (`base1`), 2.48:1 — under the 3:1 floor. Replaced
    // with Solarized's own `base00` (#657B83, 4.13:1): still canonical
    // Solarized, one step down the same ramp.
    muted: "#657B83",
  },
  {
    id: "soft-grey",
    label: "Soft grey",
    scheme: "light",
    bg: "#E9E9E7",
    ink: "#2F2F2E",
    muted: "#71716E",
  },
  {
    id: "cream",
    label: "Cream",
    scheme: "light",
    bg: "#FBF7EF",
    ink: "#33302B",
    muted: "#8C857A",
  },
  {
    id: "dawn",
    label: "Dawn",
    scheme: "light",
    bg: "#FAF4ED",
    ink: "#575279",
    // Approved as #9893A5 (Rosé Pine Dawn `muted`), 2.73:1 — under the 3:1
    // floor. Replaced with that theme's own `subtle` (#797593, 4.02:1), which
    // is the role Rosé Pine itself uses for secondary text.
    muted: "#797593",
  },
  // --- dark surfaces ---
  {
    id: "dusk",
    label: "Dusk",
    scheme: "dark",
    bg: "#1E1B18",
    ink: "#D6D0C6",
    muted: "#8A8078",
  },
  {
    id: "midnight",
    label: "Midnight",
    scheme: "dark",
    bg: "#0F1419",
    ink: "#C5CDD6",
    muted: "#7B8794",
  },
  {
    id: "black",
    label: "True black",
    scheme: "dark",
    // Pure black background, deliberately NOT pure white ink — see the module
    // note on halation. This pairing is the whole reason that rule is written
    // down.
    bg: "#000000",
    ink: "#B8B5AF",
    muted: "#6E6A64",
  },
  {
    id: "solarized-dark",
    label: "Solarized dark",
    scheme: "dark",
    bg: "#002B36",
    // Approved as #93A1A1 (`base1`), 5.61:1 — just under the 6:1 floor.
    // Lifted to 6.50:1. Solarized's own next step up is `base2` (#EEE8D5) at
    // 12.25:1, which would be far too bright for a dark surface — see the
    // "dark ink is dimmer than white on purpose" rule.
    ink: "#A1ADAD",
    muted: "#657B83",
  },
  {
    id: "forest",
    label: "Forest",
    scheme: "dark",
    bg: "#1E2326",
    ink: "#C5CDD0",
    muted: "#7A8478",
  },
  {
    id: "rose-pine",
    label: "Rosé Pine",
    scheme: "dark",
    bg: "#191724",
    ink: "#E0DEF4",
    muted: "#908CAA",
  },
];

const PALETTES_BY_ID = new Map<NovelPaletteId, NovelPalette>(
  NOVEL_PALETTES.map((palette) => [palette.id, palette]),
);

/** The default surface for each scheme, when the reader has chosen nothing. */
export const DEFAULT_LIGHT_PALETTE: NovelPaletteId = "paper";
export const DEFAULT_DARK_PALETTE: NovelPaletteId = "dusk";

export function isNovelPaletteId(value: unknown): value is NovelPaletteId {
  return typeof value === "string" && PALETTES_BY_ID.has(value as NovelPaletteId);
}

export function isNovelPaletteChoice(value: unknown): value is NovelPaletteChoice {
  return value === SITE_PALETTE || isNovelPaletteId(value);
}

export function novelPalette(id: NovelPaletteId): NovelPalette {
  const palette = PALETTES_BY_ID.get(id);
  if (!palette) throw new Error(`Unknown novel palette: ${id}`);
  return palette;
}

/**
 * The palette choice to apply right now.
 *
 * `stored` is whatever the profile picked, or `null` for "never chose one" —
 * and only then does the site theme decide, seeding Paper in a light app and
 * Dusk in a dark one. An explicit choice is never overridden by the theme: a
 * reader on Sepia stays on Sepia when the app flips to dark, which is the
 * entire point of the palette being independent.
 */
export function resolvePaletteChoice(
  stored: unknown,
  siteScheme: PaletteScheme,
): NovelPaletteChoice {
  if (isNovelPaletteChoice(stored)) return stored;
  return siteScheme === "light" ? DEFAULT_LIGHT_PALETTE : DEFAULT_DARK_PALETTE;
}

/**
 * The surface to paint, or `null` for "Follow site theme" — which is not a
 * missing palette but an explicit instruction to inherit the app's tokens, so
 * the caller renders `bg-bg`/`text-fg`/`text-muted` instead of inline colours.
 */
export function resolvePalette(choice: NovelPaletteChoice): NovelPalette | null {
  return choice === SITE_PALETTE ? null : novelPalette(choice);
}

/** Light palettes first, then dark — the order the picker lists them in. */
export function palettesByScheme(scheme: PaletteScheme): NovelPalette[] {
  return NOVEL_PALETTES.filter((palette) => palette.scheme === scheme);
}
