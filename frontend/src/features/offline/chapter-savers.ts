"use client";

import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { manifestToChapterContent, readerApi } from "@/features/reader/api";
import { readerManifestQueryKey } from "@/features/reader/hooks";
import { novelChapterQueryKey, prefetchNovelChapterWindow } from "@/features/novels/hooks";
import { buildNovelSaveRequest } from "./novel-save-request";
import { buildSaveRequest } from "./save-request";
import { resolveApiBase } from "./client";
import { useStorageScope } from "./hooks";
import type { SaveChapterRequest } from "./protocol";

/**
 * Turning a chapter KEY into a download plan, for each medium.
 *
 * Three screens list chapters — the source series page, a book's contents and
 * the library's own series page — and all three need the same two answers:
 * what to store for this chapter, and how to warm a window of them without
 * spending the rate limiter's `sources` bucket once per chapter. Written once
 * here so the three cannot drift; a saved chapter that reads offline on one
 * page and not on another would be found on a train.
 *
 * NOT exported from the feature barrel, deliberately. The barrel is imported by
 * the reader, and these pull in react-query, the reader API and the novels
 * hooks — none of which the reader's own single-chapter save needs.
 */

/** Chapters per window. The server's cap (`max_chapters`); over it is a 413. */
const WINDOW_CAP = 20;

export interface ChapterSaver {
  buildRequest: (chapterKey: string) => Promise<SaveChapterRequest | null>;
  prepare: (upcoming: readonly string[]) => Promise<void>;
}

export interface ChapterSaverInput {
  sourceId: string;
  seriesKey: string;
  seriesTitle: string | null;
  /** A chapter's own title, for the `/downloads` listing. */
  titleOf: (chapterKey: string) => string;
}

/**
 * A manga chapter: its manifest, its page images and the document that renders
 * it.
 *
 * The manifest is what makes this asynchronous — a series page does not hold
 * one — and `manifestToChapterContent` is what bakes the `?w=` the reader will
 * ask for into every page URL. That is why it is used here rather than reading
 * the raw manifest: a page has to be stored under the exact string the `<img>`
 * will request, or the chapter is fetched twice and never reads offline.
 */
export function useMangaChapterSaver({
  sourceId,
  seriesKey,
  seriesTitle,
}: Omit<ChapterSaverInput, "titleOf">): ChapterSaver {
  const queryClient = useQueryClient();
  const scope = useStorageScope();

  const buildRequest = useCallback(
    async (chapterKey: string) => {
      if (!scope || !sourceId) return null;
      const ref = { sourceId, seriesKey, chapterKey };
      const manifest = await queryClient.ensureQueryData({
        queryKey: readerManifestQueryKey(ref),
        queryFn: () => readerApi.manifest(ref),
      });
      const content = manifestToChapterContent(manifest);
      if (content.pages.length === 0) return null;
      return buildSaveRequest({
        chapter: { ...content, seriesTitle },
        scope,
        apiBase: resolveApiBase(),
        origin: window.location.origin,
        payloadJson: JSON.stringify(manifest),
      });
    },
    [queryClient, scope, seriesKey, seriesTitle, sourceId],
  );

  /**
   * `POST /reader/chapters/manifest` for a window of the run.
   *
   * `GET /reader/chapter/manifest` is on the `sources` rate-limit bucket and
   * every miss is a live scrape, so ten fired back-to-back is the naive
   * pipelining that trips it — and the 429 lands on whatever the reader opens
   * next, not on the download. The batch spends the `bulk` bucket once.
   * `strip-source.ts` runs the same endpoint for the read-all strip and is not
   * shared with it on purpose: the strip has to SURFACE a window it could not
   * load, and a warm has to stay silent, because anything it misses is still
   * fetched below.
   */
  const prepare = useCallback(
    async (upcoming: readonly string[]) => {
      if (!sourceId) return;
      const missing = upcoming
        .slice(0, WINDOW_CAP)
        .filter(
          (chapterKey) =>
            queryClient.getQueryData(
              readerManifestQueryKey({ sourceId, seriesKey, chapterKey }),
            ) === undefined,
        );
      if (missing.length === 0) return;
      try {
        const response = await readerApi.manifestBatch({ sourceId, seriesKey }, missing);
        for (const item of response.items) {
          if (item.status !== "ok" || !item.manifest) continue;
          queryClient.setQueryData(
            readerManifestQueryKey({ sourceId, seriesKey, chapterKey: item.chapter_key }),
            item.manifest,
          );
        }
      } catch {
        // Speculative: each chapter still fetches its own manifest above.
      }
    },
    [queryClient, seriesKey, sourceId],
  );

  return useMemo(() => ({ buildRequest, prepare }), [buildRequest, prepare]);
}

/**
 * A novel chapter: one JSON body, and nothing else.
 *
 * The window is doing more work here than on the manga side. A whole book is
 * hundreds of chapters, and `prefetchNovelChapterWindow` puts each one in the
 * page's cache — which `buildRequest` then hands straight to the worker as
 * `payloadJson`, so the worker stores the chapter without a request of its own.
 * A 400-chapter book is 20 POSTs rather than 400 GETs. A chapter the window
 * missed passes `null` and the worker fetches that one itself.
 */
export function useNovelChapterSaver({
  sourceId,
  seriesKey,
  seriesTitle,
  titleOf,
}: ChapterSaverInput): ChapterSaver {
  const queryClient = useQueryClient();
  const scope = useStorageScope();

  const buildRequest = useCallback(
    async (chapterKey: string) => {
      if (!scope || !sourceId) return null;
      const ref = { sourceId, seriesKey, chapterKey };
      const cached = queryClient.getQueryData(novelChapterQueryKey(ref));
      return buildNovelSaveRequest({
        ref,
        title: titleOf(chapterKey),
        seriesTitle,
        scope,
        apiBase: resolveApiBase(),
        origin: window.location.origin,
        payloadJson: cached ? JSON.stringify(cached) : null,
      });
    },
    [queryClient, scope, seriesKey, seriesTitle, sourceId, titleOf],
  );

  const prepare = useCallback(
    async (upcoming: readonly string[]) => {
      if (!sourceId) return;
      await prefetchNovelChapterWindow(queryClient, { sourceId, seriesKey }, upcoming);
    },
    [queryClient, seriesKey, sourceId],
  );

  return useMemo(() => ({ buildRequest, prepare }), [buildRequest, prepare]);
}
