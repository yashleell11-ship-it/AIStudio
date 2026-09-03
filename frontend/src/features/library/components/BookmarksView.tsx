"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useBookmarks, useDeleteBookmark } from "@/features/library/hooks";
import { readerChapterHref } from "@/features/reader/reader-link";
import { ApiError } from "@/types/api";

export function BookmarksView() {
  const bookmarksQuery = useBookmarks();
  const deleteBookmark = useDeleteBookmark();
  const [pendingId, setPendingId] = useState<number | null>(null);
  const bookmarks = bookmarksQuery.data ?? [];

  const errorMessage =
    bookmarksQuery.error instanceof ApiError
      ? bookmarksQuery.error.message
      : bookmarksQuery.error
        ? "Failed to load bookmarks."
        : null;

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

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Saved Pages</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {bookmarksQuery.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="h-20 animate-pulse rounded-lg bg-surface-2" />
                ))}
              </div>
            ) : bookmarks.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
                <p className="font-medium text-fg">No bookmarks yet</p>
                <p className="mt-2 text-sm text-muted">
                  Tap the bookmark icon in the reader to save your place on a page.
                </p>
              </div>
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
                        {new Date(bookmark.created_at).toLocaleDateString()}
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
