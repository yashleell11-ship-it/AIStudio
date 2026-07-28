import { env } from "@/config/env";
import { http } from "@/services/http";
import type {
  ChapterDetail,
  Collection,
  CollectionDetail,
  ContinueReadingItem,
  ImportResponse,
  LibraryMembership,
  MetadataQuality,
  ReadingCalendarItem,
  ReadingHistoryItem,
  RecommendationsResponse,
  ScanStatus,
  SearchResponse,
  SeriesDetail,
  SeriesFilter,
  SeriesListResponse,
  SeriesSort,
  Statistics,
  Tag,
} from "./types";

export function coverUrl(seriesId: number): string {
  return `${env.apiUrl}/library/covers/${seriesId}`;
}

export function pageImageUrl(pageId: number): string {
  return `${env.apiUrl}/reader/page/${pageId}/image`;
}

export const libraryApi = {
  // --- Series list & detail ---
  listSeries: (params: {
    page?: number;
    per_page?: number;
    sort?: SeriesSort;
    search?: string;
    status?: SeriesFilter;
    reading_status?: string;
    collection_id?: number;
    tag_id?: number;
    library_id?: number;
    is_favorite?: boolean;
    language?: string;
  }) =>
    http.get<SeriesListResponse>("/library/series", {
      query: {
        page: params.page,
        per_page: params.per_page,
        sort: params.sort,
        search: params.search || undefined,
        status: params.status && params.status !== "all" ? params.status : undefined,
        reading_status: params.reading_status || undefined,
        collection_id: params.collection_id || undefined,
        tag_id: params.tag_id || undefined,
        library_id: params.library_id || undefined,
        is_favorite: params.is_favorite != null ? String(params.is_favorite) : undefined,
        language: params.language || undefined,
      },
    }),

  getSeries: (seriesId: number) =>
    http.get<SeriesDetail>(`/library/series/${seriesId}`),

  getChapter: (chapterId: number) =>
    http.get<ChapterDetail>(`/library/chapters/${chapterId}`),

  // --- Search ---
  search: (params: { q: string; page?: number; per_page?: number }) =>
    http.get<SearchResponse>("/library/search", { query: params }),

  // --- Continue reading ---
  continueReading: (limit = 10) =>
    http.get<ContinueReadingItem[]>("/library/continue-reading", {
      query: { limit },
    }),

  // --- Favorites ---
  toggleFavorite: (seriesId: number) =>
    http.post<{ series_id: number; is_favorite: boolean }>(
      `/library/series/${seriesId}/favorite`,
    ),

  // --- Library membership ---
  // Adding/removing only flips `user_series_state.in_library` for the active
  // (user, profile): favourites, reading status and progress survive a remove,
  // so re-adding restores the shelf exactly as it was.
  addToLibrary: (seriesId: number) =>
    http.post<LibraryMembership>(`/library/series/${seriesId}/add`),

  removeFromLibrary: (seriesId: number) =>
    http.delete<LibraryMembership>(`/library/series/${seriesId}/add`),

  // --- Recommendations ---
  recommendations: (limit = 10) =>
    http.get<RecommendationsResponse>("/library/recommendations", {
      query: { limit },
    }),

  // --- Reading history ---
  readingHistory: (limit = 50) =>
    http.get<ReadingHistoryItem[]>("/library/reading-history", {
      query: { limit },
    }),

  readingCalendar: (days = 30) =>
    http.get<ReadingCalendarItem[]>("/library/reading-calendar", {
      query: { days },
    }),

  seriesReadingHistory: (seriesId: number, limit = 50) =>
    http.get<ReadingHistoryItem[]>(
      `/library/series/${seriesId}/reading-history`,
      { query: { limit } },
    ),

  // --- Statistics ---
  statistics: () => http.get<Statistics>("/library/statistics"),

  // --- Metadata ---
  updateMetadata: (seriesId: number, body: Record<string, unknown>) =>
    http.patch<SeriesDetail>(`/library/series/${seriesId}`, body),

  metadataQuality: (seriesId: number) =>
    http.get<MetadataQuality>(`/library/series/${seriesId}/metadata-quality`),

  // --- Similar ---
  similarSeries: (seriesId: number, limit = 10) =>
    http.get<SeriesDetail[]>(`/library/series/${seriesId}/similar`, {
      query: { limit },
    }),

  // --- Collections ---
  listCollections: () => http.get<Collection[]>("/library/collections"),

  getCollection: (collectionId: number) =>
    http.get<CollectionDetail>(`/library/collections/${collectionId}`),

  createCollection: (body: { name: string; description?: string }) =>
    http.post<Collection>("/library/collections", body),

  updateCollection: (
    collectionId: number,
    body: { name?: string; description?: string; sort_order?: number },
  ) =>
    http.patch<Collection>(`/library/collections/${collectionId}`, body),

  deleteCollection: (collectionId: number) =>
    http.delete<void>(`/library/collections/${collectionId}`),

  addSeriesToCollection: (collectionId: number, seriesId: number) =>
    http.post<{ collection_id: number; series_id: number }>(
      `/library/collections/${collectionId}/series/${seriesId}`,
    ),

  removeSeriesFromCollection: (collectionId: number, seriesId: number) =>
    http.delete<void>(
      `/library/collections/${collectionId}/series/${seriesId}`,
    ),

  reorderCollectionSeries: (collectionId: number, seriesIds: number[]) =>
    http.post<CollectionDetail>(
      `/library/collections/${collectionId}/reorder`,
      { series_ids: seriesIds },
    ),

  // --- Tags ---
  listTags: (category?: string) =>
    http.get<Tag[]>("/library/tags", { query: { category } }),

  createTag: (body: { name: string; category?: string; color?: string }) =>
    http.post<Tag>("/library/tags", body),

  deleteTag: (tagId: number) =>
    http.delete<void>(`/library/tags/${tagId}`),

  addTagToSeries: (seriesId: number, tagId: number) =>
    http.post<{ series_id: number; tag_id: number }>(
      `/library/series/${seriesId}/tags`,
      { tag_id: tagId },
    ),

  removeTagFromSeries: (seriesId: number, tagId: number) =>
    http.delete<void>(`/library/series/${seriesId}/tags/${tagId}`),

  // --- Import ---
  importLibrary: (folderPath: string) =>
    http.post<ImportResponse>("/library/import", { folder_path: folderPath }),

  scanStatus: () => http.get<ScanStatus>("/library/scan-status"),
};
