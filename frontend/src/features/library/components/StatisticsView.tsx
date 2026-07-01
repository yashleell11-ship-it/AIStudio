"use client";

import { useStatistics } from "@/features/library/hooks";
import { ApiError } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";

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
        <p className="mt-1 text-2xl font-bold text-fg">
          {value}
          {unit && <span className="ml-1 text-sm font-normal text-muted">{unit}</span>}
        </p>
      </CardContent>
    </Card>
  );
}

export function StatisticsView() {
  const statsQuery = useStatistics();
  const stats = statsQuery.data;

  const errorMessage =
    statsQuery.error instanceof ApiError
      ? statsQuery.error.message
      : statsQuery.error
        ? "Failed to load statistics."
        : null;

  if (statsQuery.isLoading) {
    return (
      <div className="page-shell">
        <div className="page-container">
          <div className="mb-8">
            <h1 className="page-title">Reading Statistics</h1>
          </div>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl bg-surface-2" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="page-shell">
        <div className="page-container">
          <div className="mb-8">
            <h1 className="page-title">Reading Statistics</h1>
          </div>
          {errorMessage && (
            <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
              {errorMessage}
            </div>
          )}
        </div>
      </div>
    );
  }

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

      {/* Key Stats */}
      <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
        <StatCard label="Total Series" value={stats.total_series} />
        <StatCard label="Total Chapters" value={stats.total_chapters} />
        <StatCard label="Total Pages" value={stats.total_pages.toLocaleString()} />
        <StatCard label="Completed" value={stats.completed_series} />
        <StatCard label="In Progress" value={stats.in_progress} />
        <StatCard label="Favorites" value={stats.favorites} />
        <StatCard label="Reading Streak" value={stats.reading_streak_days} unit="days" />
        <StatCard label="Pages This Week" value={stats.pages_read_this_week} />
      </div>

      {/* Completion Rate */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Completion Rate</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted">{stats.completion_rate_pct}%</span>
            <span className="text-sm text-muted">
              {stats.completed_series} / {stats.total_series} series
            </span>
          </div>
          <Progress value={stats.completion_rate_pct} className="mt-2" />
        </CardContent>
      </Card>

      {/* Weekly Chart */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Weekly Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-end gap-2"
            role="img"
            aria-label="Weekly pages read chart"
          >
            {stats.weekly_chart.map((day) => {
              const maxPages = Math.max(1, ...stats.weekly_chart.map((d) => d.pages_read));
              const height = Math.max(4, (day.pages_read / maxPages) * 120);
              return (
                <div key={day.day} className="flex flex-1 flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t bg-primary transition-all"
                    style={{ height: `${height}px` }}
                    title={`${day.label}: ${day.pages_read} pages`}
                    aria-label={`${day.label}: ${day.pages_read} pages`}
                  />
                  <span className="text-xs text-muted">{day.label}</span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Top Authors */}
      {stats.top_authors.length > 0 && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Top Authors</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {stats.top_authors.map((author) => (
                <div
                  key={author.author}
                  className="flex items-center justify-between rounded-lg border border-border px-4 py-2"
                >
                  <span className="text-sm font-medium text-fg">{author.author}</span>
                  <div className="flex items-center gap-2 text-sm text-muted">
                    <span>{author.series_count} series</span>
                    <span>·</span>
                    <span>{author.total_pages.toLocaleString()} pages</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tag Distribution */}
      {stats.tag_distribution.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Top Tags</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {stats.tag_distribution.map((tag) => (
                <Badge
                  key={tag.name}
                  variant="default"
                  style={tag.color ? { backgroundColor: tag.color + "20", borderColor: tag.color } : undefined}
                >
                  {tag.name} ({tag.series_count})
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      </div>
    </div>
  );
}
