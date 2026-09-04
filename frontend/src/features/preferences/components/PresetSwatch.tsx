import { PREVIEW_COLUMNS, type DesignPresetMeta } from "../presets";

/**
 * A miniature of the app wearing a preset.
 *
 * The mirror image of `ThemeSwatch`, and different from it in exactly one way
 * that matters. A theme swatch has to paint a palette that is NOT applied, so
 * it carries its own hexes. A preset swatch has to paint a SHAPE that is not
 * applied — but the colour it should show is the colour already on screen,
 * because the viewer is not choosing colour here. So this reads the live theme
 * roles and hard-codes only geometry.
 *
 * That asymmetry is the whole design in one component. Change the palette and
 * all five tiles repaint; change the preset and all five keep their colours.
 *
 * ### What it draws
 *
 * A shelf, because that is what the app is. The tells a viewer can actually
 * read at 90px are, in order of legibility: how many covers fit across (the
 * density axis, and the one difference that survives being shrunk), whether
 * covers or metadata lead, how much margin the frame keeps, corner radius, and
 * the heading face. Translucency and edge weight are in there too but they are
 * the honest limit of a thumbnail on a dark palette — which is why hovering a
 * tile applies the preset to the whole page instead.
 *
 * Sizes are in px rather than in `--spacing` units on purpose: the tile has to
 * look the same in every preset, including the dense one it is rendered inside
 * of, or the picker would rescale itself as you use it.
 */
export function PresetSwatch({ meta }: { meta: DesignPresetMeta }) {
  const { preview, density } = meta;
  const fill = preview.translucent ? "var(--mm-glass-card)" : "var(--color-surface-2)";
  const edge = preview.bordered
    ? `1px solid ${preview.translucent ? "var(--mm-glass-border)" : "var(--color-border)"}`
    : "1px solid transparent";
  const cell = { background: fill, border: edge, borderRadius: preview.radius };

  return (
    <span
      aria-hidden
      className="block h-[5.5rem] w-full overflow-hidden border border-border"
      style={{
        backgroundColor: "var(--color-bg)",
        borderRadius: preview.radius + 5,
      }}
    >
      <span
        className="flex h-full flex-col"
        style={{ gap: preview.gap, padding: preview.pad }}
      >
        {/* The page title. The one place a preset can change the FACE, and
            the reason Editorial is recognisable before you read the label. */}
        <span
          className="shrink-0 truncate leading-none"
          style={{
            fontFamily: preview.serif ? "var(--font-book)" : "var(--font-display)",
            fontSize: preview.serif ? 13 : 11,
            color: "var(--color-fg)",
            letterSpacing: preview.serif ? "-0.01em" : "0.05em",
          }}
        >
          Library
        </span>

        {density === "list" ? (
          /* Metadata beside the artwork: a small cover, a title line, a
             secondary line. Editorial's whole argument in three rows. */
          <span className="flex min-h-0 flex-1 flex-col" style={{ gap: preview.gap }}>
            {[0, 1, 2].map((row) => (
              <span
                key={row}
                className="flex min-h-0 flex-1 items-center"
                style={{ gap: preview.gap }}
              >
                <span className="h-full" style={{ ...cell, width: 12 }} />
                <span
                  className="flex min-w-0 flex-1 flex-col justify-center"
                  style={{ gap: 3 }}
                >
                  <span
                    className="h-[3px] rounded-full"
                    style={{ width: "62%", backgroundColor: "var(--color-fg)" }}
                  />
                  <span
                    className="h-[3px] rounded-full"
                    style={{ width: "38%", backgroundColor: "var(--color-muted)" }}
                  />
                </span>
              </span>
            ))}
          </span>
        ) : (
          /* A cover grid. `comfortable` gives three across, `compact` six —
             which is the single most legible difference between the two, and
             the same ratio the real library grid uses. */
          <span
            className="grid min-h-0 flex-1"
            style={{
              gap: preview.gap,
              gridTemplateColumns: `repeat(${PREVIEW_COLUMNS[density]}, minmax(0, 1fr))`,
              gridAutoRows: "1fr",
            }}
          >
            {Array.from({ length: PREVIEW_COLUMNS[density] * 2 }).map((_, index) => (
              <span key={index} className="min-h-0" style={cell} />
            ))}
          </span>
        )}
      </span>
    </span>
  );
}
