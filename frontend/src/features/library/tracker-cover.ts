import { env } from "@/config/env";
import type { SeriesTracker } from "@/features/updates/types";

/** Cover for a series that has been imported into the local library. */
export function seriesCoverUrl(seriesId: number): string {
  return `${env.apiUrl}/library/covers/${seriesId}`;
}

/**
 * Cover for an online source series, matching the backend route
 * `/sources/{source_id}/series/{series_id:path}/cover`.
 *
 * The series id is a source-defined string that regularly contains slashes
 * (`webtoon/lookism/123`), so it is encoded rather than interpolated raw.
 */
export function sourceSeriesCoverUrl(source: string, seriesId: string): string {
  return `${env.apiUrl}/sources/${source}/series/${encodeURIComponent(seriesId)}/cover`;
}

/**
 * Best cover for a followed series. Prefers the local library cover once the
 * series has been imported, otherwise the online source cover. Null only when
 * neither is available — the card then draws its own placeholder rather than
 * requesting an image it knows will 404.
 *
 * Mirrors `mobile/lib/features/library/utils/cover_url.dart` exactly; the two
 * clients must resolve the same series to the same URL.
 */
export function trackerCoverUrl(tracker: SeriesTracker): string | null {
  if (tracker.local_series_id != null) {
    return seriesCoverUrl(tracker.local_series_id);
  }
  if (tracker.source && tracker.series_id) {
    return sourceSeriesCoverUrl(tracker.source, tracker.series_id);
  }
  return null;
}

/** Where a followed series opens: its local detail page, else the source's. */
export function trackerHref(tracker: SeriesTracker): string {
  if (tracker.local_series_id != null) {
    return `/library/${tracker.local_series_id}`;
  }
  return `/sources/${tracker.source}/series/${encodeURIComponent(tracker.series_id)}`;
}
