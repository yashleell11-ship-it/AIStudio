"use client";

import { useCallback } from "react";
import { readerChapterHref } from "@/features/reader/reader-link";
import { useSources } from "@/features/sources/hooks";
import type { ChapterId } from "@/types/api";
import { isNovelSource } from "./gate";
import { useNovelsEnabled } from "./hooks";
import { novelChapterHref } from "./novel-link";

/**
 * "Open this chapter" — in whichever reader its source calls for.
 *
 * Every screen that links into a chapter (history, bookmarks, updates,
 * continue-reading, the series page, the command palette) needs the same
 * branch, and none of them should have to know that two readers exist. This
 * is that branch, once.
 *
 * Falls back to the manga reader whenever the answer is not yet known — the
 * sources listing has not loaded, the connector predates `content_kind`, or
 * novels are disabled entirely. In Novels mode the listing is already resolved
 * before any row renders (the mode filter needs it), so the fallback is only
 * ever reached where it is also correct.
 */
export function useChapterHref(): (ref: ChapterId, page?: number) => string {
  const novelsEnabled = useNovelsEnabled();
  const { data: sources } = useSources({ enabled: novelsEnabled });

  return useCallback(
    (ref: ChapterId, page?: number) => {
      if (!novelsEnabled || !sources) return readerChapterHref(ref, page);
      const source = sources.find((candidate) => candidate.id === ref.sourceId);
      return isNovelSource(source)
        ? novelChapterHref(ref, page)
        : readerChapterHref(ref, page);
    },
    [novelsEnabled, sources],
  );
}
