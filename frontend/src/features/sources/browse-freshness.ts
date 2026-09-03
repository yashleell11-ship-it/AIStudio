import { parseUtcTimestamp } from "@/lib/utc-time";
import type { SourceBrowseCache } from "./types";

/**
 * How a browse grid explains where its contents came from.
 *
 * `GET /sources/{id}/series` has always returned a `cache` block — the browse
 * cache serves a repeat visit without touching the connector, and serves the
 * last known page when the connector is DOWN rather than failing. The web
 * client modelled none of it, so a catalog that was hours old and a catalog
 * fetched a second ago looked identical, and "this source is unreachable, here
 * is what we saved" was indistinguishable from a live result.
 */
export type BrowseFreshnessTone = "fresh" | "stale";

export interface BrowseFreshness {
  tone: BrowseFreshnessTone;
  /** Chip text, e.g. "Updated 3 min ago". */
  label: string;
  /** The longer version, for the chip's title and assistive tech. */
  detail: string;
}

/** Coarse buckets — nobody needs "47 seconds ago" on a catalog listing. */
const JUST_NOW_MS = 45_000;
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;
/** Past this, minutes stop being the useful unit. */
const MINUTES_UNTIL_MS = 90 * 60_000;
/** Past this, hours stop being the useful unit. */
const HOURS_UNTIL_MS = 36 * HOUR_MS;

/**
 * A human age for a gap in milliseconds. A negative gap (client clock behind
 * the server's) reads as "just now" rather than a time in the future.
 */
export function formatRelativeAge(ageMs: number): string {
  if (!Number.isFinite(ageMs) || ageMs < JUST_NOW_MS) return "just now";
  if (ageMs < MINUTES_UNTIL_MS) {
    const minutes = Math.max(1, Math.round(ageMs / 60_000));
    return `${minutes} min ago`;
  }
  if (ageMs < HOURS_UNTIL_MS) {
    const hours = Math.max(1, Math.round(ageMs / HOUR_MS));
    return `${hours} h ago`;
  }
  const days = Math.max(1, Math.round(ageMs / DAY_MS));
  return `${days} d ago`;
}

/**
 * Turn a browse response's `cache` block into something worth showing, or
 * `null` when there is nothing honest to say (a search response, an older
 * backend, an unparseable timestamp).
 */
export function describeBrowseFreshness(
  cache: SourceBrowseCache | null | undefined,
  now: number,
): BrowseFreshness | null {
  if (!cache) return null;
  const fetchedAt = parseUtcTimestamp(cache.fetched_at);
  if (fetchedAt === null) return null;

  const age = formatRelativeAge(now - fetchedAt);
  // `stale` is the connector having failed, whatever the status string says.
  if (cache.stale || cache.status === "stale") {
    return {
      tone: "stale",
      label: `Saved copy · ${age}`,
      detail: `This source could not be reached, so this is the catalog last saved for it (${age}). Refresh to try the source again.`,
    };
  }
  return {
    tone: "fresh",
    label: `Updated ${age}`,
    detail:
      cache.status === "live"
        ? `Fetched from the source ${age}.`
        : `Served from the saved catalog, fetched from the source ${age}. Refresh to fetch it again now.`,
  };
}
