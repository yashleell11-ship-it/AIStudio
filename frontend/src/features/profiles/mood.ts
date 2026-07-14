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

/** The Eclipse Warm void base (matches `--color-bg-void` in globals.css). */
export const MOOD_BASE = "#0A0A0A";

/**
 * The per-mood tint, mixed at a low ratio over {@link MOOD_BASE}. Each hue is
 * muted, dark, and warm-compatible on its own so that, even blended, the result
 * reads as a tinted dark surface in the Eclipse Warm (amber/rose) family rather
 * than a saturated or cool colour. Never neon.
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
  if (!isTintedMood(mood)) return MOOD_BASE;
  const tint = MOOD_TINT[mood];
  return `radial-gradient(130% 105% at 50% -12%, color-mix(in srgb, ${tint} 24%, ${MOOD_BASE}) 0%, ${MOOD_BASE} 62%)`;
}

/**
 * A slightly stronger version of {@link moodShellBackground} for the full-bleed
 * picker, where the tint is the whole point of the screen.
 */
export function moodPickerBackground(mood: Mood): string {
  if (!isTintedMood(mood)) return MOOD_BASE;
  const tint = MOOD_TINT[mood];
  return `radial-gradient(120% 90% at 50% 0%, color-mix(in srgb, ${tint} 34%, ${MOOD_BASE}) 0%, ${MOOD_BASE} 70%)`;
}

/** A translucent accent derived from the mood tint, for rings/badges. Untinted
 * moods fall back to the Eclipse Warm amber accent (`--color-accent-amber`). */
export function moodAccent(mood: Mood, alphaPercent = 60): string {
  const tint = isTintedMood(mood) ? MOOD_TINT[mood] : "#F59E0B";
  return `color-mix(in srgb, ${tint} ${alphaPercent}%, transparent)`;
}

/** Narrow an arbitrary string to a {@link Mood}, defaulting to `"default"`. */
export function toMood(value: string | null | undefined): Mood {
  return (MOODS as readonly string[]).includes(value ?? "")
    ? (value as Mood)
    : "default";
}
