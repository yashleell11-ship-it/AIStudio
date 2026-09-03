"use client";

import Link from "next/link";
import { useState } from "react";
import { Bookmark, TriangleAlert } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { useBookmarks, useDeleteBookmark } from "@/features/library/hooks";
import { readerChapterHref } from "@/features/reader/reader-link";
import { formatUtcDate } from "@/lib/utc-time";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";

export function BookmarksView() {
  const bookmarksQuery = useBookmarks();
  const deleteBookmark = useDeleteBookmark();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const bookmarks = bookmarksQuery.data ?? [];
  const viewState = resolveViewState({
    isLoading: bookmarksQuery.isLoading,
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
          <p className="page-subtitle">Jump back into a saved page or remove ones you no longer need.</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Saved Pages</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {viewState === "loading" ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="h-20 animate-pulse rounded-lg bg-surface-2" />
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
                icon={Bookmark}
                title="No bookmarks yet"
                description="Tap the bookmark icon in the reader to save your place on a page."
                action={{ label: "Go to library", href: "/library" }}
              />
            ) : (
              bookmarks.map((bookmark) => (
                <div
                  key={bookmark.id}
                  className="flex flex-col gap-3 rounded-lg border border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <Link
                    href={readerChapterHref(
                      {
                        sourceId: bookmark.source_id,
                        seriesKey: bookmark.series_key,
                        chapterKey: bookmark.chapter_key,
                      },
                      bookmark.page,
                    )}
                    className="min-w-0"
                  >
                    <p className="font-medium text-fg hover:text-primary">
                      {bookmark.series_key}
                    </p>
                    <p className="text-sm text-muted">
                      {bookmark.chapter_key} · Page {bookmark.page}
                    </p>
                    {bookmark.note && (
                      <p className="mt-1 text-sm text-fg/80">{bookmark.note}</p>
                    )}
                    {bookmark.created_at && (
                      <p className="text-xs text-muted">
                        {formatUtcDate(bookmark.created_at)}
                      </p>
                    )}
                  </Link>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={pendingId === bookmark.id}
                    onClick={() => handleDelete(bookmark.id)}
                    className="shrink-0"
                  >
                    {pendingId === bookmark.id ? "Removing…" : "Remove"}
                  </Button>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
