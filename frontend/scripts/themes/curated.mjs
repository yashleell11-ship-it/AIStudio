/**
 * The schemes that actually ship.
 *
 * 227 of the corpus's 338 survive the contrast gate. Shipping all of them would
 * be worse than shipping none: a picker holding ninety near-identical dark
 * greys is not a feature, it is a wall, and the good ones stop being findable.
 * So the gate answers "is this legible" and this file answers "is this worth a
 * tile" — the second question has no algorithm, and pretending otherwise is how
 * you end up with `black-metal-gorgoroth` next to `windows-95`.
 *
 * The bar for inclusion: a scheme somebody would recognise and choose on
 * purpose. That is mostly the canon people actually rice with — Gruvbox, Nord,
 * Dracula, Catppuccin, Rosé Pine, Kanagawa, Everforest, Ayu, One Dark, Monokai,
 * Solarized's descendants, the editor defaults from GitHub and IBM — plus a
 * handful with a distinct enough character to earn their place (Spaceduck,
 * Eldritch, Vesper, Zenburn, Sakura).
 *
 * Deliberately NOT here, though they pass: the eleven `black-metal-*` variants
 * (identical but for one accent), `windows-95` / `windows-nt` / `linux-vt`
 * (jokes, and unreadable as an app), the eight `atelier-*` pairs and the
 * `chinoiserie` / `precious` / `da-one` families (fine schemes, but four
 * near-twins each), and every scheme whose whole identity is a single hue wash.
 *
 * `label` overrides the upstream `name` only where that name reads badly in a
 * settings list ("Gruvbox dark, hard"). `blurb` is the one line under the tile;
 * it describes the palette, not the project it came from.
 */

/** @type {{ slug: string, label?: string, blurb: string }[]} */
export const CURATED_DARK = [
  {
    slug: "gruvbox-dark-hard",
    label: "Gruvbox Hard",
    blurb: "Retro warmth — burnt orange and olive on deep brown.",
  },
  {
    slug: "gruvbox-dark-medium",
    label: "Gruvbox",
    blurb: "The classic: softer ground than Hard, same earth tones.",
  },
  {
    slug: "gruvbox-material-dark-medium",
    label: "Gruvbox Material",
    blurb: "Gruvbox with the saturation pulled back for long sessions.",
  },
  { slug: "nord", blurb: "Arctic blue-greys with frost and aurora accents." },
  { slug: "dracula", blurb: "Purple and pink on deep indigo. The famous one." },
  {
    slug: "catppuccin-mocha",
    blurb: "Pastel mauve and sky on a soft near-black.",
  },
  {
    slug: "catppuccin-macchiato",
    blurb: "Mocha's warmer, slightly lighter sibling.",
  },
  { slug: "rose-pine", blurb: "Muted rose and pine on a deep plum night." },
  { slug: "rose-pine-moon", blurb: "Rosé Pine lifted off black, gentler at night." },
  { slug: "kanagawa", blurb: "Ink-wash blues and dry gold, after Hokusai." },
  {
    slug: "everforest-dark-hard",
    label: "Everforest",
    blurb: "Low-saturation forest greens, easy on tired eyes.",
  },
  { slug: "tokyo-city-dark", label: "Tokyo City", blurb: "Neon-on-navy in the Tokyo Night lineage." },
  { slug: "ayu-dark", blurb: "Warm amber on charcoal — sharp and modern." },
  { slug: "ayu-mirage", blurb: "Ayu on slate-blue, one stop lighter." },
  { slug: "onedark-dark", label: "One Dark", blurb: "Atom's default, and half the internet's." },
  { slug: "monokai", blurb: "Sublime's green, pink and orange on graphite." },
  { slug: "material-darker", label: "Material", blurb: "Teal and coral on true dark grey." },
  { slug: "github-dark", label: "GitHub Dark", blurb: "GitHub's own dark mode, familiar and neutral." },
  { slug: "flexoki-dark", blurb: "Ink-and-paper pigments tuned for E Ink." },
  { slug: "oxocarbon-dark", label: "Oxocarbon", blurb: "IBM Carbon — cool blue with electric magenta." },
  { slug: "spaceduck", blurb: "Deep space navy with cyan and violet instruments." },
  { slug: "eldritch", blurb: "Occult greens and purples on abyssal blue." },
  { slug: "selenized-black", label: "Selenized Black", blurb: "Solarized's successor, rebuilt for true black." },
  { slug: "horizon-dark", blurb: "Dusk pinks and corals over a warm slate." },
  { slug: "zenburn", blurb: "The low-contrast original: sage and rust on grey." },
  { slug: "vesper", blurb: "Near-monochrome graphite with a single amber note." },
];

/** @type {{ slug: string, label?: string, blurb: string }[]} */
export const CURATED_LIGHT = [
  { slug: "catppuccin-latte", blurb: "Pastel accents on cool porcelain." },
  { slug: "rose-pine-dawn", blurb: "Warm blush paper with muted rose ink." },
  { slug: "gruvbox-light-medium", label: "Gruvbox Light", blurb: "Cream paper, earth-tone ink." },
  { slug: "one-light", blurb: "One Dark inverted — crisp, neutral, familiar." },
  { slug: "github", label: "GitHub Light", blurb: "GitHub's default: plain white and a confident blue." },
  { slug: "flexoki-light", blurb: "Warm paper pigments; the E Ink palette by daylight." },
  { slug: "nord-light", blurb: "Arctic blues on snow." },
  { slug: "tokyo-night-light", blurb: "The night city at noon — indigo ink on white." },
  { slug: "selenized-white", label: "Selenized White", blurb: "Solarized's successor at full brightness." },
  { slug: "equilibrium-light", blurb: "Warm oat paper balanced against a cool blue." },
  { slug: "horizon-light", blurb: "Dawn corals and pinks on warm off-white." },
  { slug: "sakura", blurb: "Blossom pink paper with deep teal ink." },
];

export const CURATED = [...CURATED_DARK, ...CURATED_LIGHT];
