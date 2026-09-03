"use client";

import { useStatistics } from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function StatCard({
  label,
  value,
  unit = "",
}: {
  label: string;
  value: string | number;
  unit?: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-sm text-muted">{label}</p>
        <p className="mt-1 font-display text-3xl tabular-nums text-primary">
          {value}
          {unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
        </p>
      </CardContent>
    </Card>
  );
}

const STATUS_LABELS: Record<string, string> = {
  unread: "Unread",
  reading: "Reading",
  completed: "Completed",
  on_hold: "On hold",
  dropped: "Dropped",
  plan_to_read: "Plan to read",
};

export function StatisticsView() {
  const statsQuery = useStatistics();
  const stats = statsQuery.data;

  const errorMessage =
    statsQuery.error instanceof ApiError
      ? statsQuery.error.message
      : statsQuery.error
        ? "Failed to load statistics."
        : null;

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Reading Statistics</h1>
          <p className="page-subtitle">Your library and reading activity at a glance.</p>
        </div>

        {errorMessage && (
          <div className="mb-6 rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        )}

        {statsQuery.isLoading ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-2" />
            ))}
          </div>
        ) : stats ? (
          <>
            <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
              <StatCard label="Followed Series" value={stats.followed_total} />
              <StatCard label="Favorites" value={stats.favorites} />
              <StatCard label="Chapters Completed" value={stats.chapters_completed} />
              <StatCard
                label="Currently Reading"
                value={stats.by_reading_status.reading ?? 0}
              />
            </div>

            {Object.keys(stats.by_reading_status).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>By Reading Status</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {Object.entries(stats.by_reading_status).map(([status, count]) => (
                      <div
                        key={status}
                        className="flex items-center justify-between rounded-lg border border-border px-4 py-2"
                      >
                        <span className="text-sm font-medium text-fg">
                          {STATUS_LABELS[status] ?? status}
                        </span>
                        <span className="text-sm tabular-nums text-muted">{count}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
