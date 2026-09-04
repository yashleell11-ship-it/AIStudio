"use client";

import Link from "next/link";
import { useState } from "react";
import { Bookmark as BookmarkIcon, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { useContentModeFilter } from "@/features/content-mode";
import { useChapterHref } from "@/features/novels/use-chapter-href";
import { formatUtcDate } from "@/lib/utc-time";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import {
  bookmarkAnchor,
  bookmarkChapterLabel,
  bookmarkMediaType,
  bookmarkPositionLabel,
  bookmarkSeriesLabel,
  withAnchorQuery,
} from "../anchor";
import { useBookmarks, useDeleteBookmark } from "../hooks";
import type { Bookmark } from "../types";

/**
 * Saved places, across both media.
 *
 * Design §5: a row has to carry enough to choose between two bookmarks
 * WITHOUT opening either — the series, the chapter, how far through it, and
 * for a novel the text at that exact point, which is the only thing that makes
 * one passage of prose distinguishable from another. All four come off the
 * listing itself; nothing here makes a second request per row.
 *
 * Opening one goes to the exact position rather than the chapter start: the
 * anchor rides in the href (`withAnchorQuery`), and the reader on the other end
 * resolves it against what the chapter holds now.
 */
export function BookmarksView() {
  const bookmarksQuery = useBookmarks();
  const deleteBookmark = useDeleteBookmark();
  const [pendingId, setPendingId] = useState<number | null>(null);
  // Scoped to the active content mode, and linked through `useChapterHref` so a
  // novel bookmark opens the novel reader. A no-op when novels are disabled.
  const { filterRows, ready: modeReady } = useContentModeFilter();
  const chapterHref = useChapterHref();
  const bookmarks = filterRows(bookmarksQuery.data, (bookmark) => bookmark.source_id);
  const viewState = resolveViewState({
    isLoading: bookmarksQuery.isLoading || !modeReady,
    error: bookmarksQuery.error,
    isEmpty: bookmarks.length === 0,
  });

  const handleDelete = async (id: number) => {
    setPendingId(id);
    try {
      await deleteBookmark.mutateAsync(id);
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Bookmarks</h1>
          <p className="page-subtitle">
            Jump back to the exact spot you saved, or remove ones you no longer need.
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Saved places</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {viewState === "loading" ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="h-24 animate-pulse rounded-lg bg-surface-2" />
                ))}
              </div>
            ) : viewState === "offline" ? (
              <OfflineState
                reason="Bookmarks need a connection to load."
                onRetry={() => void bookmarksQuery.refetch()}
              />
            ) : viewState === "error" ? (
              <EmptyState
                tone="error"
                icon={TriangleAlert}
                title="Couldn't load bookmarks"
                description={apiErrorMessage(bookmarksQuery.error, "Something went wrong.")}
                action={{ label: "Try again", onClick: () => void bookmarksQuery.refetch() }}
              />
            ) : viewState === "empty" ? (
              <EmptyState
                icon={BookmarkIcon}
                title="No bookmarks yet"
                description="Press B while reading — or use the bookmark control — to save the exact spot you are on."
                action={{ label: "Go to library", href: "/library" }}
              />
            ) : (
              bookmarks.map((bookmark) => (
                <BookmarkRow
                  key={bookmark.id}
                  bookmark={bookmark}
                  href={withAnchorQuery(
                    chapterHref({
                      sourceId: bookmark.source_id,
                      seriesKey: bookmark.series_key,
                      chapterKey: bookmark.chapter_key,
                    }),
                    bookmarkAnchor(bookmark),
                  )}
                  removing={pendingId === bookmark.id}
                  onRemove={() => handleDelete(bookmark.id)}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function BookmarkRow({
  bookmark,
  href,
  removing,
  onRemove,
}: {
  bookmark: Bookmark;
  href: string;
  removing: boolean;
  onRemove: () => void;
}) {
  const isNovel = bookmarkMediaType(bookmark.media_type) === "novel";
  const saved = formatUtcDate(bookmark.created_at);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border px-4 py-3 sm:flex-row sm:items-start sm:justify-between">
      <Link href={href} className="min-w-0 flex-1">
        <p className="truncate font-medium text-fg hover:text-primary">
          {bookmarkSeriesLabel(bookmark)}
        </p>
        <p className="text-sm text-muted">
          <span className="truncate">{bookmarkChapterLabel(bookmark)}</span>
          <span aria-hidden> · </span>
          <span className="tabular-nums">{bookmarkPositionLabel(bookmark)}</span>
        </p>

        {/* What makes a prose bookmark recognisable: the sentence it is on.
            Served by the backend from its own sanitized-text cache, so a novel
            row costs no extra request — and is simply absent for a chapter
            whose text is no longer cached. */}
        {isNovel && bookmark.snippet ? (
          <p className="mt-1.5 line-clamp-2 text-sm italic leading-snug text-fg/80">
            {bookmark.snippet}
          </p>
        ) : null}

        {/* Design §3, said once and quietly: the text moved under this
            bookmark, so opening it lands on the nearest paragraph that still
            exists rather than pretending nothing changed. */}
        {bookmark.anchor_stale ? (
          <p className="mt-1 text-xs text-muted">
            The text here changed — this opens at the nearest spot.
          </p>
        ) : null}

        {bookmark.note ? (
          <p className="mt-1 text-sm text-fg/80">{bookmark.note}</p>
        ) : null}

        {saved ? <p className="mt-1 text-xs text-muted">{saved}</p> : null}
      </Link>

      <Button
        variant="ghost"
        size="sm"
        disabled={removing}
        onClick={onRemove}
        aria-label={`Remove bookmark in ${bookmarkSeriesLabel(bookmark)}`}
        className="shrink-0"
      >
        {removing ? "Removing…" : "Remove"}
      </Button>
    </div>
  );
}
