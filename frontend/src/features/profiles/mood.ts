/**
 * Reading profile "moods" and their muted, dark background tints.
 *
 * This module is the SINGLE source of truth for the mood palette — no mood hex
 * lives anywhere else. Tints are mixed over the app's near-black base and are
 * deliberately desaturated and dark (reading-friendly, never bright). The tint
 * is applied to the app shell and the profile picker ONLY — never the reader,
 * which stays pure obsidian.
 */

/** The mood values the backend accepts for a profile (`profiles.mood`). */
export const MOODS = [
  "romantic",
  "action",
  "comedy",
  "horror",
  "slice_of_life",
  "fantasy",
  "default",
] as const;

export type Mood = (typeof MOODS)[number];

/** Human-readable labels for the picker and the management form. */
export const MOOD_LABELS: Record<Mood, string> = {
  romantic: "Romantic",
  action: "Action",
  comedy: "Comedy",
  horror: "Horror",
  slice_of_life: "Slice of Life",
  fantasy: "Fantasy",
  default: "Default",
};

/**
 * The default palette's void base (GitHub Dark's `--color-bg-void`).
 *
 * Kept in step with the bare `:root` block in globals.css: the profile picker
 * paints it as a literal `backgroundColor` under its own gradient, and a stale
 * value would show as a seam against the themed surface beside it.
 */
export const MOOD_BASE = "#0D1117";

/**
 * What the tints are actually mixed over: the ACTIVE reading theme's page
 * background, not the literal above.
 *
 * The shell paints this as an inline `background`, so it covers every surface
 * beneath it. Hard-coding the page background meant that picking Sepia or
 * Daylight left the whole app near-black with light panels floating on it — the
 * theme applied to everything except the one element drawn on top. Reading the
 * variable makes the mood a TINT over whatever the theme is, which is what a
 * mood was always meant to be.
 *
 * `MOOD_BASE` stays a literal because `MOOD_TINT.default` is a colour, and
 * because it documents what "untinted" resolves to on the default theme.
 */
export const MOOD_SURFACE = "var(--color-bg-void)";

/**
 * The per-mood tint, mixed at a low ratio over {@link MOOD_BASE}. Each hue is
 * muted, dark, and warm-compatible on its own so that, even blended, the result
 * reads as a tinted dark surface rather than a saturated or cool colour.
 * Never neon.
 */
export const MOOD_TINT: Record<Mood, string> = {
  romantic: "#7a4650", // dusty rose
  action: "#6e3228", // muted burgundy / red-brown
  comedy: "#6f5228", // warm amber-brown
  horror: "#4a3138", // deep ember oxblood
  slice_of_life: "#5b5340", // warm olive-taupe
  fantasy: "#5a4658", // dusky bronze-mauve
  default: MOOD_BASE, // the void base, untinted
};

/** True for a mood that actually tints the surface (everything but `default`). */
export function isTintedMood(mood: Mood): boolean {
  return mood !== "default" && MOOD_TINT[mood] !== MOOD_BASE;
}

/**
 * The background for the app shell under a given mood: a soft top-anchored glow
 * of the tint fading into the base. `default` returns the flat base so the
 * shell is visually identical to before profiles existed.
 */
export function moodShellBackground(mood: Mood): string {
  if (!isTintedMood(mood)) return MOOD_SURFACE;
  const tint = MOOD_TINT[mood];
  return `radial-gradient(130% 105% at 50% -12%, color-mix(in srgb, ${tint} 24%, ${MOOD_SURFACE}) 0%, ${MOOD_SURFACE} 62%)`;
}

/**
 * A slightly stronger version of {@link moodShellBackground} for the full-bleed
 * picker, where the tint is the whole point of the screen.
 */
export function moodPickerBackground(mood: Mood): string {
  if (!isTintedMood(mood)) return MOOD_SURFACE;
  const tint = MOOD_TINT[mood];
  return `radial-gradient(120% 90% at 50% 0%, color-mix(in srgb, ${tint} 34%, ${MOOD_SURFACE}) 0%, ${MOOD_SURFACE} 70%)`;
}

/** A translucent accent derived from the mood tint, for rings/badges. Untinted
 * moods fall back to the active theme's accent — read from the token rather
 * than repeated as a literal, so it follows every palette the way every other
 * accent does. */
export function moodAccent(mood: Mood, alphaPercent = 60): string {
  const tint = isTintedMood(mood) ? MOOD_TINT[mood] : "var(--color-accent-amber)";
  return `color-mix(in srgb, ${tint} ${alphaPercent}%, transparent)`;
}

/**
 * A *very* subtle wash for the reader's side margins (the gutters beside the
 * page column) — never behind the page itself, which stays pure obsidian.
 *
 * Much lower alpha than {@link moodShellBackground}: the shell tint is ambient
 * furniture, but in the reader anything with presence competes with the page.
 * `default` returns `"transparent"` so an untinted profile gets no wash at all.
 */
export function moodReaderMargin(mood: Mood): string {
  if (!isTintedMood(mood)) return "transparent";
  return `color-mix(in srgb, ${MOOD_TINT[mood]} 7%, transparent)`;
}

/** Narrow an arbitrary string to a {@link Mood}, defaulting to `"default"`. */
export function toMood(value: string | null | undefined): Mood {
  return (MOODS as readonly string[]).includes(value ?? "")
    ? (value as Mood)
    : "default";
}
