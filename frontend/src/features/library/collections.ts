/**
 * Pure view-logic for a collection's membership and its edit form.
 *
 * Membership arrives as bare `(source_id, series_key)` refs while the grid
 * draws followed-series rows, so the detail screen has to join the two. That
 * join is kept out of the view because it has a case the eye never catches:
 * `collection_series` has no foreign key to `followed_series`, so unfollowing a
 * series leaves its collection row behind. A remove UI built off the resolved
 * rows alone would list everything *except* those orphans — the one kind of
 * membership you can no longer get rid of any other way.
 */

import type { CollectionSeriesRef, FollowedSeries } from "./types";

/** The key both sides of the membership join are addressed by. */
export function seriesRefKey(sourceId: string, seriesKey: string): string {
  return `${sourceId}:${seriesKey}`;
}

export function collectionMemberKeys(
  refs: readonly CollectionSeriesRef[],
): Set<string> {
  return new Set(refs.map((ref) => seriesRefKey(ref.source_id, ref.series_key)));
}

/** One membership row, joined against the followed set. */
export interface CollectionMember {
  key: string;
  ref: CollectionSeriesRef;
  /** `null` when the series is no longer followed — an orphaned membership. */
  series: FollowedSeries | null;
  /** Always drawable: the followed title, or the raw key for an orphan. */
  label: string;
}

/** Every membership in collection order, resolved where it still can be. */
export function resolveCollectionMembers(
  refs: readonly CollectionSeriesRef[],
  followed: readonly FollowedSeries[],
): CollectionMember[] {
  const byKey = new Map(
    followed.map((series) => [
      seriesRefKey(series.source_id, series.series_key),
      series,
    ]),
  );
  return refs.map((ref) => {
    const key = seriesRefKey(ref.source_id, ref.series_key);
    const series = byKey.get(key) ?? null;
    return { key, ref, series, label: series?.title ?? ref.series_key };
  });
}

export interface CollectionDraft {
  name: string;
  description: string;
}

export interface CollectionUpdateBody {
  name?: string;
  description?: string;
}

/**
 * The `PATCH /library/collections/{id}` body for an edit, or `null` when the
 * draft says nothing new — which is what disables Save on an untouched form.
 *
 * Both fields are trimmed first. The backend's `min_length=1` on `name` passes
 * for `"   "` and only then strips it, which would leave a nameless
 * collection; a blank name is treated here as "no rename" instead, and the
 * form refuses to submit on it.
 *
 * A cleared description is sent as `""`, not omitted: the backend ignores a
 * `null` description outright, so the empty string is the only way to take one
 * back off a collection.
 */
export function collectionUpdateBody(
  current: { name: string; description: string | null },
  draft: CollectionDraft,
): CollectionUpdateBody | null {
  const name = draft.name.trim();
  const description = draft.description.trim();
  const body: CollectionUpdateBody = {};
  if (name && name !== current.name) {
    body.name = name;
  }
  if (description !== (current.description ?? "")) {
    body.description = description;
  }
  return Object.keys(body).length > 0 ? body : null;
}
