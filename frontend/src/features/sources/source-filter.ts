import type { SourcePin, SourceSummary } from "./types";

/** The scope chips above the list. Mirrors `SourcesFilter` on mobile. */
export type SourcesFilter = "all" | "pinned" | "mature";

export interface SourceRow {
  source: SourceSummary;
  /**
   * A pin whose connector no longer resolves — removed, renamed, or hidden by
   * the 18+ gate. Rendered from the pin's own metadata so it can still be
   * cleared, rather than disappearing from an ordering the reader arranged.
   */
  unavailable: boolean;
}

export interface SourceSections {
  pinned: SourceRow[];
  rest: SourceSummary[];
}

/** A stand-in row for a pin whose source is not in the visible listing. */
function placeholderSource(pin: SourcePin): SourceSummary {
  return {
    id: pin.source_id,
    name: pin.name,
    description: "",
    browsable: false,
    supports_import: false,
    icon_url: pin.icon_url,
    mature: pin.mature,
  };
}

function matches(source: SourceSummary, query: string, filter: SourcesFilter): boolean {
  if (filter === "mature" && !source.mature) return false;
  if (query === "") return true;
  const q = query.toLowerCase();
  return source.name.toLowerCase().includes(q) || source.id.toLowerCase().includes(q);
}

/**
 * Splits the installed sources into the Pinned section and everything else,
 * applying the search query and scope chip to both.
 *
 * Deliberately not re-sorted: `/sources` is already ordered case-insensitively
 * by the backend, and re-sorting client-side puts every lowercase id after
 * every uppercase one.
 *
 * The Pinned scope empties `rest` outright rather than filtering it — every
 * entry there is unpinned by definition, so filtering would leave the chip
 * inert while still rendering all ~50 rows under "All sources".
 */
export function sourceSections({
  sources,
  pins,
  query,
  filter,
}: {
  sources: SourceSummary[];
  pins: SourcePin[];
  query: string;
  filter: SourcesFilter;
}): SourceSections {
  const byId = new Map(sources.map((s) => [s.id, s]));
  const pinnedIds = new Set(pins.map((p) => p.source_id));

  const pinned: SourceRow[] = pins
    .map((pin) => {
      const found = byId.get(pin.source_id);
      return found
        ? { source: found, unavailable: false }
        : { source: placeholderSource(pin), unavailable: true };
    })
    .filter((row) => matches(row.source, query, filter));

  const rest =
    filter === "pinned"
      ? []
      : sources.filter((s) => !pinnedIds.has(s.id) && matches(s, query, filter));

  return { pinned, rest };
}
