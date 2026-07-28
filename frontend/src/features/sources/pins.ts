import type { SourcePin, SourceSummary } from "./types";

/**
 * Pure transforms over the pinned-source set.
 *
 * `PUT /sources/pins` replaces the WHOLE set in the order it is given, so every
 * edit here produces the complete next list rather than a delta — and keeps
 * `sort_order` dense, matching what the server writes back.
 */

function withDenseOrder(pins: SourcePin[]): SourcePin[] {
  return pins.map((pin, index) =>
    pin.sort_order === index ? pin : { ...pin, sort_order: index },
  );
}

export function isSourcePinned(pins: SourcePin[], sourceId: string): boolean {
  return pins.some((pin) => pin.source_id === sourceId);
}

/** Drop `sourceId` from the pinned set. Also the only way to clear a pin whose
 * source no longer resolves — there is no tile to toggle for those. */
export function removeSourcePin(pins: SourcePin[], sourceId: string): SourcePin[] {
  return withDenseOrder(pins.filter((pin) => pin.source_id !== sourceId));
}

/**
 * Pin or unpin `source`, returning the complete next set.
 *
 * A newly pinned source goes last, so pinning never reshuffles the shortcuts
 * the user already arranged. `mature` is left false on the optimistic row: the
 * installed-sources payload carries no 18+ flag, and the server's own answer
 * replaces the row as soon as the write returns.
 */
export function toggleSourcePin(pins: SourcePin[], source: SourceSummary): SourcePin[] {
  if (isSourcePinned(pins, source.id)) {
    return removeSourcePin(pins, source.id);
  }
  return [
    ...pins,
    {
      source_id: source.id,
      sort_order: pins.length,
      name: source.name,
      icon_url: source.icon_url ?? null,
      mature: false,
      // It came out of the list this profile can see, so it resolves.
      available: true,
    },
  ];
}

/** The installed sources that are not pinned, in their original order. */
export function unpinnedSources(
  sources: SourceSummary[],
  pins: SourcePin[],
): SourceSummary[] {
  const pinned = new Set(pins.map((pin) => pin.source_id));
  return sources.filter((source) => !pinned.has(source.id));
}
