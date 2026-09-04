import type { ThemeSwatch as Swatch } from "../theme-types";

/**
 * A miniature of the app wearing a palette: page, sidebar, a card with a
 * heading and a line of body text, and an accent control.
 *
 * Not three colour bars. A palette is only ever judged in situ — what matters
 * is whether the card separates from the page, whether the secondary line is
 * readable next to the primary one, and whether the accent sings or shouts
 * against both. A row of swatches answers none of those, which is why every
 * theme picker that ships one is a picker you have to try every option in.
 *
 * Painted from the theme's own hexes rather than from the live custom
 * properties, because it has to show a palette that is not applied.
 */
export function ThemeSwatch({ swatch }: { swatch: Swatch }) {
  return (
    <span
      aria-hidden
      className="block h-20 w-full overflow-hidden rounded-xl border border-border"
      style={{ backgroundColor: swatch.bg }}
    >
      <span className="flex h-full gap-1.5 p-1.5">
        {/* sidebar */}
        <span
          className="h-full w-1/5 shrink-0 rounded-md"
          style={{ backgroundColor: swatch.surface }}
        />
        <span className="flex h-full min-w-0 flex-1 flex-col gap-1.5">
          {/* a card, with a title and a line of secondary text */}
          <span
            className="flex flex-1 flex-col justify-center gap-1.5 rounded-md px-1.5"
            style={{ backgroundColor: swatch.surface }}
          >
            <span
              className="h-1 w-3/5 rounded-full"
              style={{ backgroundColor: swatch.fg }}
            />
            <span
              className="h-1 w-4/5 rounded-full"
              style={{ backgroundColor: swatch.muted }}
            />
          </span>
          {/* an accent control against the page itself */}
          <span className="flex shrink-0 items-center gap-1.5">
            <span
              className="h-2.5 w-9 rounded-full"
              style={{ backgroundColor: swatch.accent }}
            />
            <span
              className="h-2.5 flex-1 rounded-full opacity-40"
              style={{ backgroundColor: swatch.muted }}
            />
          </span>
        </span>
      </span>
    </span>
  );
}
