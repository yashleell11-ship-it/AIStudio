"use client";

import { useCallback } from "react";
import { readerChapterHref } from "@/features/reader/reader-link";
import type { ChapterId } from "@/types/api";
import { resolveNovelSource, sourceKindsKnown } from "./gate";
import { useNovelSourceKinds } from "./hooks";
import { novelChapterHref } from "./novel-link";

/** "Open this chapter", as every screen that links into one passes it around. */
export type ChapterHref = (ref: ChapterId, page?: number) => string;

/**
 * "Open this chapter" — in whichever reader its source calls for.
 *
 * Every screen that links into a chapter (history, bookmarks, updates,
 * continue-reading, the series page, statistics, the command palette) needs the
 * same branch, and none of them should have to know that two readers exist.
 * This is that branch, once.
 *
 * It always returns A link, because a function that builds an href has nothing
 * else it could return, and while the answer is unknown that link names the
 * page strip. So the fallback is a guess, not a rule — the only reason it was
 * ever safe is that the answer had already arrived. Any screen that can show a
 * NOVEL row must therefore gate its links on `useChapterLinksReady` instead of
 * drawing them and hoping.
 */
export function useChapterHref(): ChapterHref {
  const { novelsEnabled, sources } = useNovelSourceKinds();

  return useCallback(
    (ref: ChapterId, page?: number) =>
      resolveNovelSource(novelsEnabled, sources, ref.sourceId) === true
        ? novelChapterHref(ref, page)
        : readerChapterHref(ref, page),
    [novelsEnabled, sources],
  );
}

/**
 * Whether `useChapterHref` is naming readers it actually knows.
 *
 * One flag for a whole screen rather than one per row: it asks nothing about
 * any particular source, only whether the two answers behind the branch have
 * arrived. On a manga-only deployment that is the moment the novels flag says
 * off — there is no sources listing to wait for, so such a screen holds nothing
 * back and looks exactly as it did before novels existed.
 */
export function useChapterLinksReady(): boolean {
  const { novelsEnabled, sources } = useNovelSourceKinds();
  return sourceKindsKnown(novelsEnabled, sources);
}
