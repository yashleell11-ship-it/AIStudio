"use client";

import { useEffect, useRef } from "react";
import { readerDebug } from "./debug";
import {
  connectionAllowsPreload,
  shouldPreloadNextChapter,
  warmupImageUrls,
  type ConnectionHint,
} from "./preload";

export interface ChapterPreloadInput {
  /** Identity of the chapter being read; resets the once-per-chapter guard. */
  chapterKey: string;
  page: number;
  pageCount: number;
  hasNextChapter: boolean;
  /** Resolves the next chapter's payload and hands back its pages. */
  loadNextChapter: () => Promise<ReadonlyArray<{ imageUrl: string }>>;
}

/**
 * Pull the next chapter before the reader gets there, so the last page of a
 * chapter is a page turn instead of a spinner. Fires at most once per chapter
 * (see MAX_PRELOAD_CHAPTERS_AHEAD) and warms only the first few images.
 */
export function useChapterPreload({
  chapterKey,
  page,
  pageCount,
  hasNextChapter,
  loadNextChapter,
}: ChapterPreloadInput): void {
  const preloadedRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const loadRef = useRef(loadNextChapter);

  useEffect(() => {
    loadRef.current = loadNextChapter;
  }, [loadNextChapter]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!hasNextChapter) return;
    if (preloadedRef.current === chapterKey) return;
    if (!shouldPreloadNextChapter({ page, pageCount })) return;

    const connection = (navigator as Navigator & { connection?: ConnectionHint })
      .connection;
    if (!connectionAllowsPreload(connection)) {
      // Data-saver is a standing answer, not a transient one: don't re-ask.
      preloadedRef.current = chapterKey;
      return;
    }

    preloadedRef.current = chapterKey;
    readerDebug("next-chapter-preload-started", { chapterKey, page, pageCount });

    loadRef
      .current()
      .then((pages) => {
        if (!mountedRef.current || typeof window === "undefined") return;
        const urls = warmupImageUrls(pages);
        for (const url of urls) {
          const preloader = new window.Image();
          preloader.decoding = "async";
          preloader.src = url;
        }
        readerDebug("next-chapter-preload-complete", {
          chapterKey,
          pageCount: pages.length,
          warmed: urls.length,
        });
      })
      .catch(() => {
        // Best-effort: the reader still loads the chapter on navigation.
      });
  }, [chapterKey, hasNextChapter, page, pageCount]);
}
