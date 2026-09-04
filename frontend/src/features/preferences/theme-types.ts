/**
 * The shape a theme advertises to the picker.
 *
 * Its own module so `themes.generated.ts` can be typed without importing
 * `theme.ts`, which imports the generated list right back. Types-only cycles
 * compile, but a generated file that depends on the thing generated from it is
 * the kind of loop nobody wants to be holding during a rebuild.
 */

/** Whether a palette is light-on-dark or dark-on-light. */
export type ThemeScheme = "dark" | "light";

/**
 * The five colours a tile paints.
 *
 * Duplicated out of the CSS on purpose: a swatch has to show a palette that is
 * NOT currently applied, so it cannot read the live custom properties. The
 * generator writes both sides from one mapping so they cannot disagree.
 */
export interface ThemeSwatch {
  /** Page background. */
  bg: string;
  /** The raised surface a card sits on. */
  surface: string;
  /** Body text. */
  fg: string;
  /** Secondary text. */
  muted: string;
  /** The accent that carries the palette's identity. */
  accent: string;
}

/** A palette generated from a base16 scheme. */
export interface GeneratedThemeMeta {
  id: string;
  label: string;
  /** One line for the settings tile and the command palette subtitle. */
  description: string;
  /** Upstream credit, shown on the tile. Community schemes are somebody's work. */
  author: string;
  scheme: ThemeScheme;
  swatch: ThemeSwatch;
}
