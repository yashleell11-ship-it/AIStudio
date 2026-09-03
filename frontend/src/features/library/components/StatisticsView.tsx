"use client";

import { BarChart3, TriangleAlert } from "lucide-react";
import { useStatistics } from "@/features/library/hooks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";

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
  const viewState = resolveViewState({
    isLoading: statsQuery.isLoading,
    error: statsQuery.error,
    // Zero followed series means there is nothing yet for these numbers to
    // describe — a grid of stat cards reading "0" everywhere is not an
    // insight, it is a blank page with extra steps.
    isEmpty: stats != null && stats.followed_total === 0,
  });

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8">
          <h1 className="page-title">Reading Statistics</h1>
          <p className="page-subtitle">Your library and reading activity at a glance.</p>
        </div>

        {viewState === "loading" ? (
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-2" />
            ))}
          </div>
        ) : viewState === "offline" ? (
          <OfflineState
            reason="Statistics need a connection to load."
            onRetry={() => void statsQuery.refetch()}
          />
        ) : viewState === "error" ? (
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Couldn't load statistics"
            description={apiErrorMessage(statsQuery.error, "Something went wrong.")}
            action={{ label: "Try again", onClick: () => void statsQuery.refetch() }}
          />
        ) : viewState === "empty" ? (
          <EmptyState
            icon={BarChart3}
            title="Nothing to show yet"
            description="Follow a few series and start reading — your stats will build up here."
            action={{ label: "Browse Sources", href: "/sources" }}
          />
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
