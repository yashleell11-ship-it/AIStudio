import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { readerApi } from "./api";
import { readerDebug } from "./debug";

const READER_KEY = ["reader"] as const;
const READER_CHAPTER_STALE_MS = 5 * 60_000;

export function readerChapterQueryKey(chapterId: number) {
  return [...READER_KEY, "chapter", chapterId] as const;
}

export function prefetchReaderChapter(
  queryClient: ReturnType<typeof useQueryClient>,
  chapterId: number,
) {
  if (chapterId <= 0) return;
  readerDebug("api-prefetch-started", { chapterId, scope: "local" });
  void queryClient
    .prefetchQuery({
      queryKey: readerChapterQueryKey(chapterId),
      queryFn: () => readerApi.getChapter(chapterId),
      staleTime: READER_CHAPTER_STALE_MS,
    })
    .then(() => {
      readerDebug("api-prefetch-complete", { chapterId, scope: "local" });
    });
}

export function useReaderChapter(chapterId: number) {
  return useQuery({
    queryKey: readerChapterQueryKey(chapterId),
    queryFn: async () => {
      readerDebug("api-request-started", { chapterId, scope: "local" });
      const payload = await readerApi.getChapter(chapterId);
      readerDebug("api-response-received", {
        chapterId,
        scope: "local",
        pageCount: payload.page_count,
      });
      return payload;
    },
    enabled: chapterId > 0,
    staleTime: READER_CHAPTER_STALE_MS,
  });
}

export function useSaveProgress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: readerApi.saveProgress,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });
}

export function useAddBookmark() {
  return useMutation({
    mutationFn: readerApi.addBookmark,
  });
}

export function bookmarksQueryKey() {
  return [...READER_KEY, "bookmarks"] as const;
}

export function useBookmarks() {
  return useQuery({
    queryKey: bookmarksQueryKey(),
    queryFn: () => readerApi.listBookmarks(),
  });
}

export function useDeleteBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: readerApi.deleteBookmark,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: bookmarksQueryKey() });
    },
  });
}

export function useAdjacentChapter(
  chapterId: number,
  direction: "previous" | "next",
) {
  return useQuery({
    queryKey: [...READER_KEY, "adjacent", chapterId, direction],
    queryFn: () => readerApi.getAdjacentChapter(chapterId, direction),
    enabled: chapterId > 0,
  });
}
