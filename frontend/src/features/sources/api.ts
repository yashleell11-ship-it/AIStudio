import { env } from "@/config/env";
import { http } from "@/services/http";
import type {
  PaginatedSourceSeries,
  SourceBrowseMode,
  SourceGenre,
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
    http.get<SourceBrowseMode[]>(`/sources/${encodeURIComponent(sourceId)}/browse-modes`),

  genres: (sourceId: string) =>
    http.get<SourceGenre[]>(`/sources/${encodeURIComponent(sourceId)}/genres`),

  listSeries: (
    sourceId: string,
    params: { page?: number; query?: string; sort?: string; genre?: string },
  ) =>
    http.get<PaginatedSourceSeries>(
      `/sources/${encodeURIComponent(sourceId)}/series`,
      { query: params },
    ),

  getSeries: (sourceId: string, seriesId: string) =>
    http.get<SourceSeriesDetail>(
      `/sources/${encodeURIComponent(sourceId)}/series/${encodeURIComponent(seriesId)}`,
    ),

  getChapters: (sourceId: string, seriesId: string) =>
    http.get<SourceChapterSummary[]>(
      `/sources/${encodeURIComponent(sourceId)}/series/${encodeURIComponent(seriesId)}/chapters`,
    ),

  getReaderChapter: (sourceId: string, seriesId: string, chapterId: string) =>
    http.get<SourceReaderChapterResponse>(
      // Chapter ids may contain `/` (Madara/Toonily). Encode each segment so
      // the backend `:path` converter still sees the slash-separated form.
      `/sources/${encodeURIComponent(sourceId)}/series/${encodeURIComponent(seriesId)}/chapters/${chapterId
        .split("/")
        .map(encodeURIComponent)
        .join("/")}/reader`,
    ),
};
