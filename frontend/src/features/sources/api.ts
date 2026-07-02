import { env } from "@/config/env";
import { http } from "@/services/http";
import type {
  PaginatedSourceSeries,
  SourceBrowseMode,
  SourceChapterSummary,
  SourceSeriesDetail,
  SourceSummary,
} from "./types";

export function sourceImageUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const normalized = path.startsWith("/") ? path.slice(1) : path;
  return `${env.apiUrl}/${normalized}`;
}

export interface SourceReaderChapterResponse {
  mode: "local" | "remote";
  source_id: string | null;
  series_id: string;
  id: string;
  title: string;
  number: number | null;
  page_count: number;
  pages: Array<{
    id: string;
    chapter_id: string;
    number: number;
    width: number | null;
    height: number | null;
    image_url: string;
  }>;
  previous_chapter_id: string | null;
  next_chapter_id: string | null;
  series_title?: string | null;
}

export const sourcesApi = {
  listSources: () => http.get<SourceSummary[]>("/sources"),

  browseModes: (sourceId: string) =>
    http.get<SourceBrowseMode[]>(`/sources/${sourceId}/browse-modes`),

  listSeries: (
    sourceId: string,
    params: { page?: number; query?: string; sort?: string },
  ) => http.get<PaginatedSourceSeries>(`/sources/${sourceId}/series`, { query: params }),

  getSeries: (sourceId: string, seriesId: string) =>
    http.get<SourceSeriesDetail>(`/sources/${sourceId}/series/${seriesId}`),

  getChapters: (sourceId: string, seriesId: string) =>
    http.get<SourceChapterSummary[]>(`/sources/${sourceId}/series/${seriesId}/chapters`),

  getReaderChapter: (sourceId: string, seriesId: string, chapterId: string) =>
    http.get<SourceReaderChapterResponse>(
      `/sources/${sourceId}/series/${seriesId}/chapters/${chapterId}/reader`,
    ),
};
