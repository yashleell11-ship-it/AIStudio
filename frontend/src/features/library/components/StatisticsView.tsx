"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  BarChart3,
  BookOpen,
  Clock,
  Flame,
  Layers,
  TriangleAlert,
} from "lucide-react";
import { useContentModeFilter, type ContentMode } from "@/features/content-mode";
import { libraryCoverUrl } from "@/features/library/api";
import { useStatistics } from "@/features/library/hooks";
import {
  activeDaysInWindow,
  bestDay,
  chapterLabel,
  DEFAULT_STATISTICS_RANGE,
  formatCount,
  formatDuration,
  formatHourLabel,
  formatHourRange,
  hasReadingHistory,
  hourlyBars,
  isStatisticsEmpty,
  isWindowEmpty,
  peakHour,
  readingStatusBreakdown,
  scopeBreakdowns,
  seriesTitle,
  showsPageCounts,
  sourceShares,
  statisticsScopeNote,
  STATISTICS_RANGE_LABELS,
  STATISTICS_RANGES,
  type StatisticsRange,
} from "@/features/library/reading-stats";
import type {
  DailyReading,
  RecentSession,
  SeriesReading,
  Statistics,
} from "@/features/library/types";
// Direct rather than through the `@/features/novels` barrel, which also pulls
// in the novel reader — this screen only links into it, it never renders it.
import {
  useChapterHref,
  useChapterLinksReady,
  type ChapterHref,
} from "@/features/novels/use-chapter-href";
import { seriesPageHref } from "@/features/reader/reader-link";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { OfflineState } from "@/components/ui/offline-state";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/cn";
import { formatCalendarDay, formatUtcDate, formatUtcDateTime } from "@/lib/utc-time";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { ActivityChart } from "./ActivityChart";

/**
 * What `reading_sessions` has been recording all along.
 *
 * The screen this replaces showed four numbers off the follow table, none of
 * which described reading — the session table had been written to for months
 * and read by nothing. It now leads with the window's activity, gives the daily
 * series a real chart, and keeps the original library shape at the bottom where
 * it belongs.
 *
 * Two clocks run through the payload and they are handled differently on
 * purpose: `*_at` fields are naive-UTC instants (`formatUtc*`), while
 * `daily[].date` and `streak.last_active_date` are calendar days the backend
 * already bucketed at the offset we sent (`formatCalendarDay`). See
 * `lib/utc-time.ts` — sending either through the other's parser is a 5.5-hour
 * bug in IST, and this codebase has shipped it twice.
 */

// ---------------------------------------------------------------------------
// Pieces
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
  caption,
}: {
  icon: typeof BookOpen;
  label: string;
  value: string;
  caption: string;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-muted">
          <Icon className="size-4 shrink-0" aria-hidden />
          <p className="text-sm">{label}</p>
        </div>
        <p className="mt-2 font-display text-3xl tabular-nums text-primary">{value}</p>
        <p className="mt-1 text-xs text-muted">{caption}</p>
      </CardContent>
    </Card>
  );
}

function SectionCard({
  title,
  aside,
  children,
  className,
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <CardTitle>{title}</CardTitle>
        {aside ? <div className="text-xs text-muted">{aside}</div> : null}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

/** "Nothing in this section yet" — quieter than a whole-page empty state. */
function SectionNote({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}

function StreakCard({ stats, daily }: { stats: Statistics; daily: DailyReading[] }) {
  const { streak } = stats;
  // The tail of the window, so the dots always end on today.
  const recentDays = daily.slice(-14);
  const activeDays = activeDaysInWindow(daily);

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <div>
            <p className="flex items-center gap-2 text-sm text-muted">
              <Flame className="size-4" aria-hidden />
              Current streak
            </p>
            <p className="mt-1 font-display text-3xl tabular-nums text-primary">
              {streak.current_days}
              <span className="ml-1.5 font-sans text-sm font-normal text-muted">
                {streak.current_days === 1 ? "day" : "days"}
              </span>
            </p>
          </div>
          <div>
            <p className="text-sm text-muted">Longest</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-fg">
              {streak.longest_days}
              <span className="ml-1.5 font-sans text-sm font-normal text-muted">
                {streak.longest_days === 1 ? "day" : "days"}
              </span>
            </p>
          </div>
          <div>
            <p className="text-sm text-muted">Days read</p>
            <p className="mt-1 font-display text-2xl tabular-nums text-fg">
              {activeDays}
              <span className="ml-1.5 font-sans text-sm font-normal text-muted">
                of {daily.length}
              </span>
            </p>
          </div>
        </div>

        <div className="shrink-0 sm:text-right">
          <div className="flex items-center gap-1 sm:justify-end" aria-hidden>
            {recentDays.map((day) => (
              <span
                key={day.date}
                title={`${formatCalendarDay(day.date, { invalid: day.date })} — ${
                  day.sessions > 0 ? `${formatCount(day.pages_read)} pages` : "nothing read"
                }`}
                className={cn(
                  "size-2.5 rounded-full",
                  day.sessions > 0 ? "bg-primary" : "bg-fg/15",
                )}
              />
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">
            {streak.last_active_date
              ? `Last read ${formatCalendarDay(streak.last_active_date, {
                  invalid: streak.last_active_date,
                })}`
              : "Not read yet"}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function HourHistogram({ stats }: { stats: Statistics }) {
  const bars = hourlyBars(stats.by_hour);
  const peak = peakHour(stats.by_hour);
  const anyReading = bars.some((bar) => bar.sessions > 0);

  return (
    <SectionCard
      title="When you read"
      aside={peak ? `Peak ${formatHourRange(peak.hour)}` : undefined}
    >
      {anyReading ? (
        <>
          <div className="flex h-32 items-end gap-[3px]">
            {bars.map((bar) => (
              <div
                key={bar.hour}
                className="flex h-full flex-1 items-end"
                title={`${formatHourRange(bar.hour)} — ${formatCount(
                  bar.pages_read,
                )} pages, ${formatDuration(bar.seconds_read)}`}
              >
                <div
                  className={cn(
                    "w-full rounded-sm",
                    bar.fraction > 0 ? "bg-primary" : "bg-fg/10",
                  )}
                  style={{
                    // A read hour is never invisible: 6% floor, then the real share.
                    height: bar.fraction > 0 ? `${6 + bar.fraction * 94}%` : "2px",
                    opacity: bar.fraction > 0 ? 0.45 + bar.fraction * 0.55 : 1,
                  }}
                />
              </div>
            ))}
          </div>
          <div className="mt-2 flex justify-between text-[11px] text-muted">
            <span>{formatHourLabel(0)}</span>
            <span>{formatHourLabel(6)}</span>
            <span>{formatHourLabel(12)}</span>
            <span>{formatHourLabel(18)}</span>
            <span>{formatHourLabel(23)}</span>
          </div>
          <p className="sr-only">
            {peak
              ? `Most reading happens between ${formatHourRange(peak.hour)}.`
              : "No reading recorded in this window."}
          </p>
        </>
      ) : (
        <SectionNote>Nothing read in this window yet.</SectionNote>
      )}
    </SectionCard>
  );
}

function SourceBreakdown({
  stats,
  showPages,
}: {
  stats: Statistics;
  showPages: boolean;
}) {
  const shares = sourceShares(stats.by_source);

  return (
    <SectionCard title="Where you read">
      {shares.length > 0 ? (
        <ul className="space-y-3">
          {shares.map((source) => (
            <li key={source.source_id}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate text-sm font-medium text-fg">{source.name}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted">
                  {showPages
                    ? `${formatCount(source.pages_read)} pages`
                    : `${formatCount(source.chapters_read)} ${
                        source.chapters_read === 1 ? "chapter" : "chapters"
                      }`}{" "}
                  · {formatDuration(source.seconds_read)}
                </span>
              </div>
              <Progress
                value={source.percent}
                className="mt-1.5"
                aria-label={`${source.name}: ${Math.round(source.percent)}% of reading in this window`}
              />
            </li>
          ))}
        </ul>
      ) : (
        <SectionNote>Nothing read in this window yet.</SectionNote>
      )}
    </SectionCard>
  );
}

function SeriesRow({ row, showPages }: { row: SeriesReading; showPages: boolean }) {
  const ref = { sourceId: row.source_id, seriesKey: row.series_key };
  return (
    <li className="flex items-center gap-3">
      <div className="relative h-16 w-11 shrink-0 overflow-hidden rounded-md bg-surface-2 ring-1 ring-white/5">
        {row.cover_url ? (
          <Image
            src={libraryCoverUrl(row.cover_url, "44px")}
            alt=""
            fill
            className="object-cover"
            sizes="44px"
            unoptimized
          />
        ) : (
          <span className="flex h-full items-center justify-center text-muted" aria-hidden>
            <BookOpen className="size-4" />
          </span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <Link
          href={seriesPageHref(ref)}
          className="block truncate text-sm font-medium text-fg hover:text-primary"
        >
          {seriesTitle(row)}
        </Link>
        <p className="mt-0.5 text-xs tabular-nums text-muted">
          {showPages ? `${formatCount(row.pages_read)} pages · ` : ""}
          {formatCount(row.chapters_read)}{" "}
          {row.chapters_read === 1 ? "chapter" : "chapters"} · {formatDuration(row.seconds_read)}
        </p>
        {row.last_read_at ? (
          <p className="mt-0.5 text-xs text-muted">Last read {formatUtcDate(row.last_read_at)}</p>
        ) : null}
      </div>
    </li>
  );
}

function RecentSessionRow({
  row,
  chapterHref,
  showPages,
}: {
  row: RecentSession;
  chapterHref: ChapterHref;
  showPages: boolean;
}) {
  const ref = {
    sourceId: row.source_id,
    seriesKey: row.series_key,
    chapterKey: row.chapter_key,
  };
  return (
    <li className="flex flex-col gap-1 rounded-lg border border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <Link
          href={seriesPageHref(ref)}
          className="block truncate text-sm font-medium text-fg hover:text-primary"
        >
          {seriesTitle(row)}
        </Link>
        <Link
          href={chapterHref(ref)}
          className="text-xs text-primary hover:underline"
        >
          {chapterLabel(row)}
        </Link>
      </div>
      <div className="shrink-0 text-xs text-muted sm:text-right">
        <p className="tabular-nums">
          {showPages
            ? `${formatCount(row.pages_read)} ${row.pages_read === 1 ? "page" : "pages"} · `
            : ""}
          {formatDuration(row.seconds_read)}
        </p>
        <p>{formatUtcDateTime(row.started_at, { missing: "Unknown" })}</p>
      </div>
    </li>
  );
}

function LibraryShape({ stats }: { stats: Statistics }) {
  const statuses = readingStatusBreakdown(stats.by_reading_status);
  return (
    <SectionCard
      title="Your library"
      aside={`${formatCount(stats.followed_total)} followed · ${formatCount(
        stats.favorites,
      )} favourites · ${formatCount(stats.chapters_completed)} chapters finished`}
    >
      {statuses.length > 0 ? (
        <ul className="space-y-3">
          {statuses.map((status) => (
            <li key={status.status}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-medium text-fg">{status.label}</span>
                <span className="shrink-0 text-xs tabular-nums text-muted">
                  {formatCount(status.count)}
                </span>
              </div>
              <Progress
                value={status.percent}
                className="mt-1.5"
                aria-label={`${status.label}: ${status.count} of ${stats.followed_total} series`}
              />
            </li>
          ))}
        </ul>
      ) : (
        <SectionNote>Nothing followed yet.</SectionNote>
      )}
    </SectionCard>
  );
}

function RangePicker({
  value,
  onChange,
}: {
  value: StatisticsRange;
  onChange: (next: StatisticsRange) => void;
}) {
  return (
    <div
      className="inline-flex rounded-lg border border-border/50 bg-white/[0.03] p-1"
      role="group"
      aria-label="Statistics window"
    >
      {STATISTICS_RANGES.map((range) => (
        <button
          key={range}
          type="button"
          onClick={() => onChange(range)}
          aria-pressed={range === value}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
            range === value
              ? "bg-primary text-primary-fg"
              : "text-muted hover:bg-white/5 hover:text-fg",
          )}
        >
          {STATISTICS_RANGE_LABELS[range]}
        </button>
      ))}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl bg-surface-2" />
        ))}
      </div>
      <div className="h-24 animate-pulse rounded-xl bg-surface-2" />
      <div className="h-80 animate-pulse rounded-xl bg-surface-2" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-64 animate-pulse rounded-xl bg-surface-2" />
        <div className="h-64 animate-pulse rounded-xl bg-surface-2" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

export function StatisticsView() {
  const [range, setRange] = useState<StatisticsRange>(DEFAULT_STATISTICS_RANGE);
  const statsQuery = useStatistics(range);
  // Scoped to the active content mode the way every other list screen is, and
  // a no-op when the server has novels off. Only the three source-carrying
  // lists move — see `scopeBreakdowns` for why the aggregates do not.
  const { keepSource, ready: modeReady, mode, novelsEnabled } = useContentModeFilter();
  // Recent sessions link into a chapter, so this screen carries the same
  // "which reader?" answer every other linking screen does — and the same wait
  // for it. In Novels mode a guess here is not one wrong row, it is all of them.
  const chapterHref = useChapterHref();
  const linksReady = useChapterLinksReady();
  const stats = useMemo(
    () => (statsQuery.data ? scopeBreakdowns(statsQuery.data, keepSource) : undefined),
    [keepSource, statsQuery.data],
  );

  const viewState = resolveViewState({
    // Held on `modeReady` so the breakdowns are never drawn against an empty
    // source index, which in Novels mode is every row filtered out: a frame of
    // "nothing read yet" before the real lists arrive. `linksReady` is the same
    // bargain for the session links, and adds no wait a manga-only deployment
    // can see: it is satisfied the moment the novels flag says off.
    isLoading: statsQuery.isLoading || !modeReady || !linksReady,
    error: statsQuery.error,
    // Empty means the profile has NEVER read and follows nothing — the common
    // case on a fresh profile, and the one case where a grid of zeroes would
    // be a blank page with extra steps. A profile that follows series but has
    // not read yet keeps its library section and gets a targeted note instead;
    // so does one whose history is simply older than the selected window.
    isEmpty: stats != null && isStatisticsEmpty(stats),
  });

  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="page-title">Reading Statistics</h1>
            <p className="page-subtitle">
              What you have actually read, from every session recorded on this profile.
            </p>
          </div>
          {viewState === "content" ? (
            <RangePicker value={range} onChange={setRange} />
          ) : null}
        </div>

        {viewState === "loading" ? (
          <LoadingSkeleton />
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
            title="No reading recorded yet"
            description="This page is built from your reading sessions — every chapter you open is timed and counted. Follow a series, read a chapter, and your streak, daily activity and reading hours start filling in from the first page."
            action={{ label: "Browse Sources", href: "/sources" }}
            secondaryAction={{ label: "Go to library", href: "/library", variant: "secondary" }}
          />
        ) : stats ? (
          <StatisticsContent
            stats={stats}
            range={range}
            mode={mode}
            novelsEnabled={novelsEnabled}
            chapterHref={chapterHref}
          />
        ) : null}
      </div>
    </div>
  );
}

function StatisticsContent({
  stats,
  range,
  mode,
  novelsEnabled,
  chapterHref,
}: {
  stats: Statistics;
  range: StatisticsRange;
  mode: ContentMode;
  novelsEnabled: boolean;
  chapterHref: ChapterHref;
}) {
  const rangeLabel = STATISTICS_RANGE_LABELS[range].toLowerCase();
  const showPages = showsPageCounts(mode, novelsEnabled);
  const scopeNote = statisticsScopeNote(mode, novelsEnabled);
  const everRead = hasReadingHistory(stats);
  const windowEmpty = isWindowEmpty(stats);
  const peak = bestDay(stats.daily);
  const cap = stats.range.session_cap_seconds;

  if (!everRead) {
    return (
      <div className="space-y-6">
        <EmptyState
          icon={BookOpen}
          title="Nothing read on this profile yet"
          description={`You follow ${formatCount(
            stats.followed_total,
          )} ${stats.followed_total === 1 ? "series" : "series"}, but no chapter has been opened yet. Read one and this page fills in with your streak, daily activity, reading hours and most-read series.`}
          action={{ label: "Go to library", href: "/library" }}
        />
        <LibraryShape stats={stats} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* The lists below are scoped to the mode and the numbers above them are
          not, and the pages figure inside those numbers is adding page images
          to prose reading positions. Saying both costs one line and is the
          whole difference between a deliberate split and a page that looks
          wrong. */}
      {scopeNote ? <p className="text-sm text-muted">{scopeNote}</p> : null}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          icon={BookOpen}
          label="Pages read"
          value={formatCount(stats.window.pages_read)}
          caption={`${formatCount(stats.totals.pages_read)} all time`}
        />
        <StatCard
          icon={Clock}
          label="Time read"
          value={formatDuration(stats.window.seconds_read)}
          caption={`${formatDuration(stats.totals.seconds_read)} all time`}
        />
        <StatCard
          icon={Layers}
          label="Chapters"
          value={formatCount(stats.window.chapters_read)}
          caption={`${formatCount(stats.chapters_completed)} finished all time`}
        />
        <StatCard
          icon={BarChart3}
          label="Series"
          value={formatCount(stats.window.series_read)}
          caption={`${formatCount(stats.followed_total)} followed`}
        />
      </div>

      <StreakCard stats={stats} daily={stats.daily} />

      <SectionCard
        title="Activity"
        aside={
          peak
            ? `Best day ${formatCalendarDay(peak.date, { invalid: peak.date })} · ${formatCount(
                peak.pages_read,
              )} pages`
            : `Last ${rangeLabel}`
        }
      >
        {windowEmpty ? (
          <SectionNote>
            Nothing read in the last {rangeLabel}. Your all-time totals are above — pick a
            longer window, or open a chapter to start a new streak.
          </SectionNote>
        ) : (
          <ActivityChart daily={stats.daily} />
        )}
      </SectionCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <HourHistogram stats={stats} />
        <SourceBreakdown stats={stats} showPages={showPages} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard title="Most read" aside={`Last ${rangeLabel}`}>
          {stats.by_series.length > 0 ? (
            <ul className="space-y-3">
              {stats.by_series.map((row) => (
                <SeriesRow
                  key={`${row.source_id}:${row.series_key}`}
                  row={row}
                  showPages={showPages}
                />
              ))}
            </ul>
          ) : (
            <SectionNote>Nothing read in this window yet.</SectionNote>
          )}
        </SectionCard>

        <SectionCard title="Recent sessions" aside="All time">
          {stats.recent_sessions.length > 0 ? (
            <ul className="space-y-2">
              {stats.recent_sessions.map((row) => (
                <RecentSessionRow
                  key={`${row.source_id}:${row.series_key}:${row.chapter_key}:${row.started_at}`}
                  row={row}
                  chapterHref={chapterHref}
                  showPages={showPages}
                />
              ))}
            </ul>
          ) : (
            <SectionNote>No sessions recorded yet.</SectionNote>
          )}
        </SectionCard>
      </div>

      <LibraryShape stats={stats} />

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <Badge>
          Days start at UTC
          {stats.range.timezone_offset_minutes >= 0 ? "+" : "−"}
          {String(Math.floor(Math.abs(stats.range.timezone_offset_minutes) / 60)).padStart(2, "0")}
          :
          {String(Math.abs(stats.range.timezone_offset_minutes) % 60).padStart(2, "0")}
        </Badge>
        <span>
          Reading time counts each session up to {formatDuration(cap)}, so a chapter left
          open on a locked screen is not counted as reading.
        </span>
        {stats.totals.first_session_at ? (
          <span>· Recording since {formatUtcDate(stats.totals.first_session_at)}.</span>
        ) : null}
      </div>
    </div>
  );
}
