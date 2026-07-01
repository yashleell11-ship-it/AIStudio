"use client";

import Link from "next/link";
import { useReadingCalendar, useReadingHistory } from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function ReadingHistoryView() {
  const historyQuery = useReadingHistory(50);
  const calendarQuery = useReadingCalendar(30);
  const history = historyQuery.data ?? [];
  const calendar = calendarQuery.data ?? [];

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
        <p className="page-subtitle">Track your reading sessions and activity.</p>
      </div>

      {errorMessage && (
        <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {errorMessage}
        </div>
      )}

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Last 30 Days</CardTitle>
        </CardHeader>
        <CardContent>
          {calendarQuery.isLoading ? (
            <div className="grid grid-cols-7 gap-1" aria-busy="true">
              {Array.from({ length: 35 }).map((_, index) => (
                <div key={index} className="h-14 animate-pulse rounded-lg bg-surface-2" />
              ))}
            </div>
          ) : calendar.length === 0 ? (
            <p className="text-sm text-muted">No reading activity in the last 30 days.</p>
          ) : (
            <>
              <div className="mb-2 grid grid-cols-7 gap-1 text-center text-xs text-muted">
                {WEEKDAYS.map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>
              <div className="grid grid-cols-7 gap-1">
                {calendar.map((day) => (
                  <div
                    key={day.day}
                    title={`${day.day}: ${day.pages_read} pages`}
                    className={`flex flex-col items-center gap-1 rounded-lg p-2 ${
                      day.has_activity
                        ? "bg-primary/10 text-primary"
                        : "bg-surface-2 text-muted"
                    }`}
                  >
                    <span className="text-xs">{day.day.slice(8)}</span>
                    <span className="text-sm font-semibold">{day.pages_read}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Sessions</CardTitle>
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
              <p className="font-medium text-fg">No reading sessions yet</p>
              <p className="mt-2 text-sm text-muted">
                Open a chapter from your library to start tracking sessions.
              </p>
            </div>
          ) : (
            history.map((session) => (
              <div
                key={session.session_id}
                className="flex flex-col gap-3 rounded-lg border border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0">
                  <Link
                    href={`/library/${session.series_id}`}
                    className="font-medium text-fg hover:text-primary"
                  >
                    {session.series_title ?? "Unknown Series"}
                  </Link>
                  <p className="text-sm text-muted">
                    {session.chapter_title ?? "Unknown Chapter"}
                  </p>
                  <p className="text-xs text-muted">
                    Pages {session.start_page}–{session.end_page} ·{" "}
                    {session.pages_read} pages read
                  </p>
                </div>
                <div className="shrink-0 sm:text-right">
                  {session.started_at && (
                    <p className="text-xs text-muted">
                      {new Date(session.started_at).toLocaleDateString()}
                    </p>
                  )}
                  <Badge variant="primary" className="mt-1">
                    {session.pages_read} pages
                  </Badge>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      </div>
    </div>
  );
}
