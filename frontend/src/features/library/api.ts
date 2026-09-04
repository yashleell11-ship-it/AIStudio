import { env } from "@/config/env";
import { http } from "@/services/http";
import type { SeriesId } from "@/types/api";
import type {
  Bookmark,
  Collection,
  CollectionDetail,
  ContinueReadingItem,
  FollowedSeries,
  RecommendationsResponse,
  SearchResponse,
  SeriesDetail,
  SeriesFilter,
  SeriesListResponse,
  SeriesSort,
  Statistics,
  Tag,
} from "./types";

/**
 * Resolve a cover URL from a followed-series payload. The backend returns
 * either an absolute source URL or a backend-relative proxy path
 * (`/sources/{source}/series/{series}/cover`); the relative form is resolved
 * against the API base here.
 */
export function libraryCoverUrl(coverUrl: string): string {
  if (/^https?:\/\//i.test(coverUrl)) return coverUrl;
  return `${env.apiUrl}${coverUrl.startsWith("/") ? "" : "/"}${coverUrl}`;
}

/** Source cover proxy for a `(source, series_key)` with no payload in hand. */
export function seriesCoverUrl({ sourceId, seriesKey }: SeriesId): string {
  return `${env.apiUrl}/sources/${encodeURIComponent(sourceId)}/series/${encodeURIComponent(
    seriesKey,
  )}/cover`;
}

export const libraryApi = {
  // --- Followed series list & detail ---
  listSeries: (params: {
    page?: number;
    per_page?: number;
    sort?: SeriesSort;
    search?: string;
    status?: SeriesFilter;
    reading_status?: string;
    is_favorite?: boolean;
  }) =>
    http.get<SeriesListResponse>("/library/series", {
      query: {
        page: params.page,
        per_page: params.per_page,
        sort: params.sort,
        search: params.search || undefined,
        reading_status:
          params.reading_status ||
          (params.status && params.status !== "all" ? params.status : undefined),
        is_favorite:
          params.is_favorite != null ? String(params.is_favorite) : undefined,
      },
    }),

  getSeries: (followedId: number) =>
    http.get<SeriesDetail>(`/library/series/${followedId}`),

  // --- Follow / unfollow ---
  follow: (ref: SeriesId) =>
    http.post<FollowedSeries>("/library/follow", {
      source_id: ref.sourceId,
      series_key: ref.seriesKey,
    }),

  unfollow: (followedId: number) =>
    http.delete<void>(`/library/follow/${followedId}`),

  patchSeries: (
    followedId: number,
    body: {
      is_favorite?: boolean;
      reading_status?: string;
      notify?: boolean;
      mature_override?: boolean;
      sort_order?: number;
    },
  ) => http.patch<FollowedSeries>(`/library/series/${followedId}`, body),

  // --- Strips / discovery ---
  continueReading: (limit = 10) =>
    http.get<ContinueReadingItem[]>("/library/continue-reading", {
      query: { limit },
    }),

  recentlyUpdated: (limit = 10) =>
    http.get<FollowedSeries[]>("/library/recently-updated", { query: { limit } }),

  recommendations: (limit = 10) =>
    http.get<RecommendationsResponse>("/library/recommendations", {
      query: { limit },
    }),

  /**
   * Library shape + reading activity. `tz_offset_minutes` decides where a day
   * starts for the daily buckets, the hour histogram and the streak — the
   * backend stores naive UTC and will not guess, so the caller has to say.
   */
  statistics: (params: { days: number; tz_offset_minutes: number }) =>
    http.get<Statistics>("/library/statistics", { query: params }),

  // --- Search over the followed set ---
  search: (params: { q: string; page?: number; per_page?: number }) =>
    http.get<SearchResponse>("/library/search", { query: params }),

  // --- Reading history (progress service) ---
  readingHistory: (limit = 50, offset = 0) =>
    http.get<import("./types").ReadingHistoryItem[]>("/reader/history", {
      query: { limit, offset },
    }),

  // --- Bookmarks (progress service) ---
  listBookmarks: (ref?: Partial<SeriesId>) =>
    http.get<Bookmark[]>("/reader/bookmarks", {
      query: {
        source: ref?.sourceId,
        series: ref?.seriesKey,
      },
    }),

  deleteBookmark: (bookmarkId: number) =>
    http.delete<void>(`/reader/bookmarks/${bookmarkId}`),

  // --- Collections ---
  listCollections: () => http.get<Collection[]>("/library/collections"),

  getCollection: (collectionId: number) =>
    http.get<CollectionDetail>(`/library/collections/${collectionId}`),

  createCollection: (body: { name: string; description?: string }) =>
    http.post<Collection>("/library/collections", body),

  updateCollection: (
    collectionId: number,
    body: { name?: string; description?: string; sort_order?: number },
  ) => http.patch<Collection>(`/library/collections/${collectionId}`, body),

  deleteCollection: (collectionId: number) =>
    http.delete<void>(`/library/collections/${collectionId}`),

  addSeriesToCollection: (collectionId: number, ref: SeriesId) =>
    http.post<CollectionDetail>(`/library/collections/${collectionId}/series`, {
      source_id: ref.sourceId,
      series_key: ref.seriesKey,
    }),

  removeSeriesFromCollection: (collectionId: number, ref: SeriesId) =>
    http.delete<void>(`/library/collections/${collectionId}/series`, {
      body: { source_id: ref.sourceId, series_key: ref.seriesKey },
    }),

  // --- Tags ---
  listTags: (category?: string) =>
    http.get<Tag[]>("/library/tags", { query: { category } }),

  createTag: (body: { name: string; category?: string; color?: string }) =>
    http.post<Tag>("/library/tags", body),

  deleteTag: (tagId: number) => http.delete<void>(`/library/tags/${tagId}`),

  addTagToSeries: (ref: SeriesId, tagId: number) =>
    http.post<{ source_id: string; series_key: string; tag_id: number }>(
      "/library/series-tags",
      { source_id: ref.sourceId, series_key: ref.seriesKey, tag_id: tagId },
    ),

  removeTagFromSeries: (ref: SeriesId, tagId: number) =>
    http.delete<void>("/library/series-tags", {
      body: { source_id: ref.sourceId, series_key: ref.seriesKey, tag_id: tagId },
    }),
};
