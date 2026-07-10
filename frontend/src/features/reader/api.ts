import { env } from "@/config/env";
import { http } from "@/services/http";
import type { ChapterDetail, ReadingProgress } from "@/features/library/types";
import type { ReaderChapterContent, ReaderPage } from "./types";

export type { ReadingProgress };

export interface Bookmark {
  id: number;
  series_id: number;
  series_title?: string | null;
  chapter_id: number;
  chapter_title?: string | null;
  page: number;
  note: string | null;
  created_at: string;
}

export interface AdjacentChapter {
  id: number;
  series_id: number;
  title: string;
  number: number | null;
}

export function readerPageImageUrl(pageId: number): string {
  return `${env.apiUrl}/reader/page/${pageId}/image`;
}

export function toReaderChapterContent(chapter: ChapterDetail): ReaderChapterContent {
  return {
    id: String(chapter.id),
    seriesId: String(chapter.series_id),
    title: chapter.title,
    pageCount: chapter.page_count,
    mode: "local",
    sourceId: null,
    previousChapterId: null,
    nextChapterId: null,
    pages: chapter.pages.map(
      (page): ReaderPage => ({
        id: String(page.id),
        number: page.number,
        imageUrl: readerPageImageUrl(page.id),
        width: page.width ?? null,
        height: page.height ?? null,
      }),
    ),
  };
}

export function toRemoteReaderChapterContent(payload: {
  mode: "local" | "remote";
  source_id: string | null;
  series_id: string;
  id: string;
  title: string;
  page_count: number;
  pages: Array<{
    id: string;
    number: number;
    width: number | null;
    height: number | null;
    image_url: string;
  }>;
  previous_chapter_id: string | null;
  next_chapter_id: string | null;
  series_title?: string | null;
}): ReaderChapterContent {
  return {
    id: payload.id,
    seriesId: payload.series_id,
    title: payload.title,
    pageCount: payload.page_count,
    mode: payload.mode,
    sourceId: payload.source_id,
    seriesTitle: payload.series_title,
    previousChapterId: payload.previous_chapter_id,
    nextChapterId: payload.next_chapter_id,
    pages: payload.pages.map((page) => ({
      id: page.id,
      number: page.number,
      width: page.width,
      height: page.height,
      imageUrl: page.image_url.startsWith("http")
        ? page.image_url
        : `${env.apiUrl}${page.image_url}`,
    })),
  };
}

export const readerApi = {
  getChapter: (chapterId: number) =>
    http.get<ChapterDetail>(`/reader/chapter/${chapterId}`),

  saveProgress: (payload: {
    series_id: number;
    chapter_id: number;
    last_page: number;
  }) => http.post<ReadingProgress>("/reader/progress", payload),

  getProgress: (seriesId: number) =>
    http.get<ReadingProgress | null>(`/reader/progress/${seriesId}`),

  addBookmark: (payload: {
    series_id: number;
    chapter_id: number;
    page: number;
    note?: string;
  }) => http.post<Bookmark>("/reader/bookmarks", payload),

  listBookmarks: (limit = 200) =>
    http.get<Bookmark[]>("/reader/bookmarks", { query: { limit } }),

  deleteBookmark: (bookmarkId: number) =>
    http.delete<void>(`/reader/bookmarks/${bookmarkId}`),

  getAdjacentChapter: (chapterId: number, direction: "previous" | "next") =>
    http.get<AdjacentChapter | null>(`/reader/chapter/${chapterId}/adjacent`, {
      query: { direction },
    }),
};
