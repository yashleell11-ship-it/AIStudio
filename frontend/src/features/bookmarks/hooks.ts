"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { SeriesId } from "@/types/api";
import { bookmarksApi } from "./api";
import type { Bookmark, BookmarkCreate } from "./types";

export const BOOKMARKS_KEY = ["bookmarks"] as const;

export function bookmarksQueryKey(ref?: Partial<SeriesId>) {
  return [...BOOKMARKS_KEY, "list", ref?.sourceId ?? null, ref?.seriesKey ?? null] as const;
}

/**
 * Every live bookmark in the active profile, newest change first (the server's
 * default ordering for a listing with no `?since=`).
 *
 * `staleTime: 0` because capture and delete both write straight into this list
 * and both invalidate it: a cached answer from before the bookmark that was
 * just saved is exactly the "I pressed b and nothing happened" bug.
 */
export function useBookmarks(ref?: Partial<SeriesId>) {
  return useQuery({
    queryKey: bookmarksQueryKey(ref),
    queryFn: () => bookmarksApi.list(ref),
    staleTime: 0,
  });
}

export function useDeleteBookmark() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookmarkId: number) => bookmarksApi.remove(bookmarkId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BOOKMARKS_KEY });
    },
  });
}

/** How long the "Saved" confirmation stays up after a capture. */
export const CAPTURE_ACKNOWLEDGEMENT_MS = 2200;

export interface BookmarkCapture {
  /** Capture the position described by `body`. One action, no dialog. */
  capture: (body: BookmarkCreate) => void;
  /** A request is in flight. */
  pending: boolean;
  /** A capture just landed — drives the transient confirmation. */
  justSaved: boolean;
  /** Why the last capture failed, or null. */
  failed: boolean;
}

/**
 * The capture side of a bookmark, for both readers.
 *
 * Shared rather than written twice because the readers differ only in how they
 * work out the anchor — the mutation, the cache invalidation and the "it
 * worked" acknowledgement are identical, and the acknowledgement is the part
 * that would otherwise be skipped in one of them. `justSaved` is a timed flag
 * rather than the mutation's own `isSuccess` so that bookmarking the same spot
 * twice, or two spots in a row, re-shows the confirmation instead of leaving a
 * stale one on screen.
 */
export function useBookmarkCapture(): BookmarkCapture {
  const queryClient = useQueryClient();
  const [justSaved, setJustSaved] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const mutation = useMutation({
    mutationFn: (body: BookmarkCreate) => bookmarksApi.create(body),
    onSuccess: (bookmark: Bookmark) => {
      void queryClient.invalidateQueries({ queryKey: BOOKMARKS_KEY });
      if (timerRef.current) clearTimeout(timerRef.current);
      setJustSaved(true);
      timerRef.current = setTimeout(
        () => setJustSaved(false),
        CAPTURE_ACKNOWLEDGEMENT_MS,
      );
      return bookmark;
    },
  });

  const { mutate } = mutation;
  const capture = useCallback(
    (body: BookmarkCreate) => {
      setJustSaved(false);
      mutate(body);
    },
    [mutate],
  );

  return {
    capture,
    pending: mutation.isPending,
    justSaved,
    failed: mutation.isError && !mutation.isPending,
  };
}
