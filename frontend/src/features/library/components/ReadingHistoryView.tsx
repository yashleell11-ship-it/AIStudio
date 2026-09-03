"use client";

import Link from "next/link";
import { useReadingHistory } from "@/features/library/hooks";
import { readerChapterHref, seriesPageHref } from "@/features/reader/reader-link";
import { ApiError } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function ReadingHistoryView() {
  const historyQuery = useReadingHistory(50);
  const history = historyQuery.data ?? [];

  const errorMessage =
    historyQuery.error instanceof ApiError
      ? historyQuery.error.message
      : historyQuery.error
        ? "Failed to load reading history."
        : null;

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Reading History</h1>
          <p className="page-subtitle">Everything you have read, most recent first.</p>
        </div>

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Recent Chapters</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {historyQuery.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 5 }).map((_, index) => (
                  <div key={index} className="h-20 animate-pulse rounded-lg bg-surface-2" />
                ))}
              </div>
            ) : history.length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-surface p-8 text-center">
                <p className="font-medium text-fg">Nothing read yet</p>
                <p className="mt-2 text-sm text-muted">
                  Open a chapter from your library to start tracking history.
                </p>
              </div>
            ) : (
              history.map((entry) => {
                const ref = {
                  sourceId: entry.source_id,
                  seriesKey: entry.series_key,
                  chapterKey: entry.chapter_key,
                };
                return (
                  <div
                    key={entry.id}
                    className="flex flex-col gap-3 rounded-lg border border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0">
                      <Link
                        href={seriesPageHref(ref)}
                        className="font-medium text-fg hover:text-primary"
                      >
                        {entry.series_key}
                      </Link>
                      <p className="text-sm text-muted">
                        {entry.chapter_number != null
                          ? `Chapter ${entry.chapter_number}`
                          : entry.chapter_key}
                      </p>
                      <Link
                        href={readerChapterHref(ref, entry.last_page)}
                        className="text-xs text-primary hover:underline"
                      >
                        Resume at page {entry.last_page}
                        {entry.page_count > 0 ? ` / ${entry.page_count}` : ""}
                      </Link>
                    </div>
                    <div className="shrink-0 sm:text-right">
                      {entry.last_read_at && (
                        <p className="text-xs text-muted">
                          {new Date(entry.last_read_at).toLocaleDateString()}
                        </p>
                      )}
                      {entry.is_completed ? (
                        <Badge variant="primary" className="mt-1">
                          Completed
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
