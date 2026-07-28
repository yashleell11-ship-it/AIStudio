/**
 * Deciding whether a LOCAL series page can offer Follow, and what that control
 * should say.
 *
 * Follow used to exist only on the source-browse page, so a *downloaded*
 * series — the one the owner cared enough to download, and the one you land on
 * from a downloaded chapter — could not be followed at all: no update checks,
 * no new-chapter notifications. `GET /library/series/{id}` now states the
 * origin (`source_id`/`source_series_id`) and this profile's follow state
 * (`is_followed`/`follow_tracker_id`) on every detail payload, which is
 * everything the control needs.
 *
 * Kept React-free and side-effect-free so it can be unit tested directly, and
 * so the only React it touches is types (`import type`, erased at compile
 * time) — the component owns the hooks.
 */
import type { SeriesTracker } from "@/features/updates/types";
import type { SeriesDetail } from "./types";

/**
 * A local series' origin plus the follow state the payload arrived with.
 *
 * Its existence *is* the render decision: a series with no origin has nothing
 * to follow, so there is no link and no control (see
 * {@link resolveSeriesFollowLink}).
 */
export interface SeriesFollowLink {
  /** Connector id — the tracker API calls this field `source`. */
  sourceId: string;
  /** The connector's own series id — the tracker API calls this `series_id`. */
  sourceSeriesId: string;
  /** Follow state as of this payload; the control's first-paint answer. */
  seedIsFollowed: boolean;
  /** Tracker backing `seedIsFollowed`, or null when not followed. */
  seedTrackerId: number | null;
}

/**
 * The origin of a local series, or `null` when it has none.
 *
 * `null` means *omit the control entirely* rather than render it disabled: a
 * hand-imported CBZ folder has genuinely nothing to track, and a greyed-out
 * Follow button with no explanation is a worse answer than no button.
 *
 * Both ids are required even though the backend guarantees they are both set
 * or both null: `POST /updates/trackers/follow` needs the pair, so half a link
 * cannot produce a working button — and offering one that 422s is worse than
 * offering none.
 */
export function resolveSeriesFollowLink(
  series: SeriesDetail | null | undefined,
): SeriesFollowLink | null {
  const sourceId = series?.source_id;
  const sourceSeriesId = series?.source_series_id;
  if (!sourceId || !sourceSeriesId) {
    return null;
  }
  const trackerId = series?.follow_tracker_id ?? null;
  return {
    sourceId,
    sourceSeriesId,
    // `is_followed` without a tracker id is a state the control cannot act on:
    // Unfollow is `DELETE /updates/trackers/{id}` and there would be no id to
    // send. Rendering Follow instead is the recoverable direction — following
    // something already followed returns the existing tracker rather than
    // duplicating it (backend/services/update_service.py:490).
    seedIsFollowed: series?.is_followed === true && trackerId !== null,
    seedTrackerId: series?.is_followed === true ? trackerId : null,
  };
}

/** What the Follow control renders and acts on right now. */
export interface FollowControlState {
  isFollowed: boolean;
  /** Tracker to unfollow. Non-null exactly when `isFollowed` is true. */
  trackerId: number | null;
}

/**
 * Merge the payload's follow state with the live followed-trackers cache.
 *
 * Two sources of truth, deliberately: the payload is the only one available on
 * first paint (so the button reads "Unfollow" immediately for an
 * already-followed series instead of flashing "Follow" until the tracker list
 * arrives), while the tracker list is the only one that reflects a
 * follow/unfollow the user just performed — that mutation patches the tracker
 * cache optimistically, and the detail payload does not catch up until its
 * refetch lands.
 *
 * So: the list wins once it has loaded, the payload answers until then. That is
 * why `trackersLoaded` is a separate argument — "no tracker because the list is
 * empty" and "no tracker because the list has not arrived" are the same
 * `undefined` from the lookup, and treating the second as "not followed" is
 * exactly the flash this exists to prevent.
 *
 * @param tracker The row for this series from `useFollowedTracker`, if any.
 * @param trackersLoaded Whether `useTrackers("followed")` has data at all. False
 *   while it is in flight *and* if it failed — a failed list must not downgrade
 *   the payload's own server answer to "not followed".
 */
export function resolveFollowControlState(
  link: SeriesFollowLink,
  tracker: SeriesTracker | undefined,
  trackersLoaded: boolean,
): FollowControlState {
  if (!trackersLoaded) {
    return { isFollowed: link.seedIsFollowed, trackerId: link.seedTrackerId };
  }
  return { isFollowed: tracker !== undefined, trackerId: tracker?.id ?? null };
}
