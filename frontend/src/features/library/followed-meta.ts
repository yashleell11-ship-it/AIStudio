import { chapterLabel } from "@/features/sources/chapter-label";
import type { SeriesTracker, UpdateNotification } from "@/features/updates/types";

/**
 * Everything a Library card can say *truthfully* about a followed series
 * without firing a per-series network request.
 *
 * `SeriesTracker.known_chapter_count` is written only by the backend update
 * checker, so a freshly-followed series — or one whose connector is erroring —
 * reports 0 even though the series has hundreds of chapters. Rendering
 * "0 chapters" is therefore a lie, and the only way to get a real count here
 * would be one chapter-list request per followed series on every Library open.
 * Instead we surface what the already-loaded updates payload knows: the newest
 * chapter we have ever been notified about, and how many of those notifications
 * are still unread.
 *
 * Mirrors `FollowedSeriesMeta` in
 * `mobile/lib/features/library/widgets/home/followed_series_card.dart`.
 */
export interface FollowedSeriesMeta {
  /**
   * Unread new-chapter notifications for this tracker, counted from the same
   * notification page the Updates tab renders — so the two always agree.
   */
  unreadCount: number;
  /**
   * Label of the newest chapter we have been notified about ("Chapter 120"),
   * or null when the series has never produced a notification.
   */
  latestChapterLabel: string | null;
}

export const NO_FOLLOWED_META: FollowedSeriesMeta = {
  unreadCount: 0,
  latestChapterLabel: null,
};

/**
 * Newest-first ordering: chapter number when both sides have one, else the
 * creation timestamp, else insertion id.
 */
function isNewer(a: UpdateNotification, b: UpdateNotification): boolean {
  if (a.chapter_number != null && b.chapter_number != null && a.chapter_number !== b.chapter_number) {
    return a.chapter_number > b.chapter_number;
  }
  if (a.created_at && b.created_at && a.created_at !== b.created_at) {
    return Date.parse(a.created_at) > Date.parse(b.created_at);
  }
  return a.id > b.id;
}

/** Derives the meta for `tracker` from the already-loaded notifications. */
export function followedSeriesMeta(
  tracker: SeriesTracker,
  notifications: readonly UpdateNotification[],
): FollowedSeriesMeta {
  let unreadCount = 0;
  let latest: UpdateNotification | null = null;

  for (const notification of notifications) {
    if (notification.tracker_id !== tracker.id) continue;
    if (!notification.is_read) unreadCount += 1;
    if (latest === null || isNewer(notification, latest)) {
      latest = notification;
    }
  }

  return {
    unreadCount,
    latestChapterLabel:
      latest === null
        ? null
        : chapterLabel({ number: latest.chapter_number, title: latest.chapter_title }).primary,
  };
}

/**
 * The one muted line under a card: the latest chapter we actually know about,
 * else a chapter count only when the checker has populated one, else nothing
 * at all rather than a "0 chapters" that is not true.
 */
export function followedSubtitle(
  tracker: SeriesTracker,
  meta: FollowedSeriesMeta,
): string | null {
  if (meta.latestChapterLabel) {
    return `Latest: ${meta.latestChapterLabel}`;
  }
  const known = tracker.known_chapter_count;
  if (known <= 0) return null;
  return known === 1 ? "1 chapter" : `${known} chapters`;
}
