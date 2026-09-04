"use client";

import Link from "next/link";
import { History, TriangleAlert } from "lucide-react";
import { useContentModeFilter } from "@/features/content-mode";
import { useReadingHistory } from "@/features/library/hooks";
import { useChapterHref } from "@/features/novels/use-chapter-href";
import { chapterPercent } from "@/features/novels/progress";
import { seriesPageHref } from "@/features/reader/reader-link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { formatUtcDate } from "@/lib/utc-time";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";

export function ReadingHistoryView() {
  const historyQuery = useReadingHistory(50);
  // Scoped to the active content mode, and linked through `useChapterHref` so a
  // novel row opens the novel reader. A no-op when novels are disabled.
  const { filterRows, ready: modeReady, mode } = useContentModeFilter();
  const chapterHref = useChapterHref();
  const history = filterRows(historyQuery.data, (entry) => entry.source_id);
  const viewState = resolveViewState({
    isLoading: historyQuery.isLoading || !modeReady,
    error: historyQuery.error,
    isEmpty: history.length === 0,
  });

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Reading History</h1>
          <p className="page-subtitle">Everything you have read, most recent first.</p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Recent Chapters</CardTitle>
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
                reason="Reading history needs a connection to load."
                onRetry={() => void historyQuery.refetch()}
              />
            ) : viewState === "error" ? (
              <EmptyState
                tone="error"
                icon={TriangleAlert}
                title="Couldn't load reading history"
                description={apiErrorMessage(historyQuery.error, "Something went wrong.")}
                action={{ label: "Try again", onClick: () => void historyQuery.refetch() }}
              />
            ) : viewState === "empty" ? (
              <EmptyState
                icon={History}
                title="Nothing read yet"
                description="Open a chapter from your library and it will show up here as you go."
                action={{ label: "Go to library", href: "/library" }}
              />
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
                        href={chapterHref(ref, entry.last_page)}
                        // The row's actual action, and at `text-xs` its line
                        // box is 16px tall — the smallest thing on the screen
                        // is the one thing anyone comes here to press. Given
                        // real height on touch only, so the desktop row keeps
                        // its density.
                        className="inline-flex items-center text-xs text-primary hover:underline [@media(pointer:coarse)]:min-h-11 [@media(pointer:coarse)]:pr-3"
                      >
                        {/* A novel has no pages: its position is a progress
                            bucket, so it reads back as a percentage. */}
                        {mode === "novel"
                          ? `Resume at ${chapterPercent(entry.last_page, entry.page_count)}%`
                          : `Resume at page ${entry.last_page}${entry.page_count > 0 ? ` / ${entry.page_count}` : ""}`}
                      </Link>
                    </div>
                    <div className="shrink-0 sm:text-right">
                      {entry.last_read_at && (
                        <p className="text-xs text-muted">
                          {formatUtcDate(entry.last_read_at)}
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
