import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import type { ChapterId } from "@/types/api";
import { manifestToChapterContent, readerApi, type ProgressPush } from "./api";
import type { ReaderPage } from "./types";

const READER_KEY = ["reader"] as const;
const READER_CHAPTER_STALE_MS = 5 * 60_000;

export function readerManifestQueryKey(ref: ChapterId) {
  return [
    ...READER_KEY,
    "manifest",
    ref.sourceId,
    ref.seriesKey,
    ref.chapterKey,
  ] as const;
}

export function useChapterManifest(ref: ChapterId | null) {
  return useQuery({
    queryKey: ref
      ? readerManifestQueryKey(ref)
      : [...READER_KEY, "manifest", "none"],
    queryFn: () => readerApi.manifest(ref!),
    enabled: ref !== null,
    staleTime: READER_CHAPTER_STALE_MS,
  });
}

/** Warm a chapter's manifest into the cache and hand back its pages. */
export async function ensureChapterPages(
  queryClient: QueryClient,
  ref: ChapterId,
): Promise<ReadonlyArray<ReaderPage>> {
  const manifest = await queryClient.ensureQueryData({
    queryKey: readerManifestQueryKey(ref),
    queryFn: () => readerApi.manifest(ref),
  });
  return manifestToChapterContent(manifest).pages;
}

export function prefetchChapterManifest(
  queryClient: QueryClient,
  ref: ChapterId,
) {
  void queryClient.prefetchQuery({
    queryKey: readerManifestQueryKey(ref),
    queryFn: () => readerApi.manifest(ref),
    staleTime: READER_CHAPTER_STALE_MS,
  });
}

export function useSaveProgress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ref,
      body,
    }: {
      ref: ChapterId;
      body: Omit<ProgressPush, "source_id" | "series_key" | "chapter_key">;
    }) => readerApi.saveProgress(ref, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["library"] });
    },
  });
}

export function useAddBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ref,
      page,
      note,
    }: {
      ref: ChapterId;
      page: number;
      note?: string;
    }) => readerApi.addBookmark(ref, page, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...READER_KEY, "bookmarks"] });
    },
  });
}
