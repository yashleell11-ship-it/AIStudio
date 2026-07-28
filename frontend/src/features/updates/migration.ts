import { ApiError } from "@/types/api";
import type { MigrationCounts, MigrationPlan } from "./types";

/**
 * Pure helpers for the source-migration flow — kept out of the dialog so the
 * two error paths the endpoint can take on commit are unit-testable.
 */

function errorDetails(error: unknown): Record<string, unknown> | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  return typeof error.details === "object" && error.details !== null
    ? (error.details as Record<string, unknown>)
    : null;
}

/**
 * The id of the follow that already points at the chosen target, or null when
 * that is not why the commit failed.
 *
 * The server refuses by default rather than merging: the two follows can carry
 * different notify / auto-download / interval settings and different known
 * chapters, and silently picking a winner is what later shows up as "it stopped
 * notifying me". Merging stays available as an explicit opt-in.
 */
export function migrationConflictTrackerId(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.code !== "tracker_target_already_followed") {
    return null;
  }
  const existing = errorDetails(error)?.existing_tracker_id;
  return typeof existing === "number" ? existing : null;
}

/**
 * The freshly recomputed plan carried by a `migration_stale` refusal, or null.
 *
 * The target gained or lost chapters between preview and confirm, so the map
 * the user approved is no longer the map that would be applied. The server
 * returns the new one instead of applying something nobody saw.
 */
export function stalePreviewFromError(error: unknown): MigrationPlan | null {
  if (!(error instanceof ApiError) || error.code !== "migration_stale") {
    return null;
  }
  const preview = errorDetails(error)?.preview;
  if (
    typeof preview === "object" &&
    preview !== null &&
    typeof (preview as MigrationPlan).chapter_map_hash === "string"
  ) {
    return preview as MigrationPlan;
  }
  return null;
}

/** One-line description of what a plan would carry over. */
export function migrationSummary(counts: MigrationCounts): string {
  const base = `${counts.matched} of ${counts.old} chapters map onto the target's ${counts.new}`;
  return counts.dropped > 0
    ? `${base} · ${counts.dropped} cannot be carried over`
    : `${base} · nothing is left behind`;
}

/**
 * Parse the chapter-offset field. Returns null for input that is not a finite
 * number, so the caller can refuse to preview rather than silently send 0 —
 * an offset of 0 and a typo produce very different maps.
 */
export function parseChapterOffset(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return 0;
  }
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}
