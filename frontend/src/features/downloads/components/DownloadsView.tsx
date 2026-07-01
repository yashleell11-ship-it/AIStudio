"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  X,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import {
  groupDownloadsBySeries,
  seriesCanCancel,
  seriesCanPause,
  seriesCanResume,
  visibleGroupItems,
} from "../grouping";
import {
  useCancelAllDownloads,
  useCancelDownload,
  useCancelSeries,
  useDownloadMetrics,
  useDownloads,
  usePauseAllDownloads,
  usePauseDownload,
  usePauseSeries,
  useResumeAllDownloads,
  useResumeDownload,
  useResumeSeries,
  useRetryDownload,
} from "../hooks";
import type { DownloadItem, SeriesDownloadGroup } from "../types";

type FilterTab = "all" | "downloading" | "queued" | "paused" | "failed";

const HIDDEN_FROM_QUEUE = new Set(["completed", "cancelled"]);

function formatBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatSpeed(speedBps: number | null | undefined, speedMbps: number | null | undefined): string {
  if (speedMbps && speedMbps > 0) {
    return `${speedMbps.toFixed(1)} MB/s`;
  }
  if (!speedBps || speedBps <= 0) {
    return "—";
  }
  return `${formatBytes(speedBps)}/s`;
}

function formatEta(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

function statusLabel(status: string): string {
  if (status === "failed") {
    return "Error";
  }
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function statusBadgeClass(status: string): string {
  switch (status) {
    case "downloading":
      return "border-violet-500/40 bg-violet-500/15 text-violet-400";
    case "queued":
      return "border-cyan-500/40 bg-cyan-500/15 text-cyan-400";
    case "paused":
      return "border-amber-500/40 bg-amber-500/15 text-amber-400";
    case "failed":
      return "border-danger/40 bg-danger/15 text-danger";
    case "completed":
      return "border-success/40 bg-success/15 text-success";
    default:
      return "border-border bg-surface-2 text-muted";
  }
}

function matchesFilter(item: DownloadItem, filter: FilterTab): boolean {
  if (HIDDEN_FROM_QUEUE.has(item.status)) {
    return false;
  }
  if (filter === "all") {
    return true;
  }
  if (filter === "failed") {
    return item.status === "failed";
  }
  return item.status === filter;
}

function filterCount(items: DownloadItem[], filter: FilterTab): number {
  return items.filter((item) => matchesFilter(item, filter)).length;
}

function seriesInitials(title: string): string {
  const words = title.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return "?";
  }
  if (words.length === 1) {
    return words[0].slice(0, 2).toUpperCase();
  }
  return `${words[0][0]}${words[1][0]}`.toUpperCase();
}

function GradientProgress({
  value,
  className,
  "aria-label": ariaLabel,
}: {
  value: number;
  className?: string;
  "aria-label"?: string;
}) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-white/5", className)}
      role="progressbar"
      aria-label={ariaLabel}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function StatTile({
  label,
  value,
  icon: Icon,
  accent = "violet",
}: {
  label: string;
  value: string;
  icon?: React.ComponentType<{ className?: string }>;
  accent?: "violet" | "cyan" | "emerald" | "amber";
}) {
  const accentStyles = {
    violet: "from-violet-500/20 to-violet-500/5 text-violet-400",
    cyan: "from-cyan-500/20 to-cyan-500/5 text-cyan-400",
    emerald: "from-emerald-500/20 to-emerald-500/5 text-emerald-400",
    amber: "from-amber-500/20 to-amber-500/5 text-amber-400",
  };

  return (
    <div className="glass-card rounded-xl p-3">
      {Icon && (
        <div
          className={cn(
            "mb-2 flex size-8 items-center justify-center rounded-lg bg-gradient-to-br",
            accentStyles[accent],
          )}
        >
          <Icon className="size-3.5" />
        </div>
      )}
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums text-fg">{value}</p>
    </div>
  );
}

function DownloadThumbnail({ title }: { title: string }) {
  return (
    <div className="relative flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-violet-600/30 to-cyan-500/20 ring-1 ring-white/10">
      <span className="font-display text-lg tracking-wide text-white/90">
        {seriesInitials(title)}
      </span>
    </div>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
  tone = "violet",
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  tone?: "violet" | "cyan" | "amber" | "danger";
}) {
  const toneActive = {
    violet: "border-violet-500/50 bg-violet-500/20 text-violet-300",
    cyan: "border-cyan-500/50 bg-cyan-500/20 text-cyan-300",
    amber: "border-amber-500/50 bg-amber-500/20 text-amber-300",
    danger: "border-danger/50 bg-danger/20 text-danger",
  };
  const toneIdle = {
    violet: "hover:border-violet-500/30 hover:text-violet-400",
    cyan: "hover:border-cyan-500/30 hover:text-cyan-400",
    amber: "hover:border-amber-500/30 hover:text-amber-400",
    danger: "hover:border-danger/30 hover:text-danger",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/[0.03] px-4 py-2 text-sm transition-all duration-200",
        active ? toneActive[tone] : cn("text-muted", toneIdle[tone]),
      )}
    >
      {label}
      <span
        className={cn(
          "rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
          active ? "bg-white/10" : "bg-white/5",
        )}
      >
        {count}
      </span>
    </button>
  );
}

function DownloadRow({
  item,
  onPause,
  onResume,
  onCancel,
  onRetry,
  busy,
}: {
  item: DownloadItem;
  onPause: (id: number) => void;
  onResume: (id: number) => void;
  onCancel: (id: number) => void;
  onRetry: (id: number) => void;
  busy: boolean;
}) {
  const isActive = item.status === "downloading" || item.status === "queued";

  return (
    <div className="glass-card rounded-xl p-4 transition-colors hover:border-violet-500/20">
      <div className="flex gap-4">
        <DownloadThumbnail title={item.series_title} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium text-fg">{item.series_title}</p>
              <p className="mt-0.5 truncate text-sm text-muted">{item.chapter_title}</p>
            </div>
            <span
              className={cn(
                "inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize",
                statusBadgeClass(item.status),
              )}
            >
              {item.status === "downloading" && (
                <span className="mr-1.5 size-1.5 animate-pulse rounded-full bg-violet-400" />
              )}
              {statusLabel(item.status)}
            </span>
          </div>

          <div className="mt-3 space-y-2">
            <GradientProgress
              value={item.progress}
              aria-label={`${item.chapter_title} download progress`}
            />
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
              <div className="flex flex-wrap items-center gap-3">
                <span className="tabular-nums">
                  {item.pages_done}/{item.pages_total || "?"} pages
                </span>
                {item.status === "downloading" && (
                  <span className="inline-flex items-center gap-1 text-cyan-400">
                    <Zap className="size-3" aria-hidden />
                    {formatSpeed(item.speed_bps, item.speed_mbps)}
                  </span>
                )}
                {item.status === "downloading" && item.eta_seconds != null && item.eta_seconds > 0 && (
                  <span>ETA {formatEta(item.eta_seconds)}</span>
                )}
              </div>
              <div className="flex items-center gap-3 tabular-nums">
                <span className="font-medium text-fg">{item.progress.toFixed(0)}%</span>
                <span>{formatBytes(item.bytes_downloaded)}</span>
              </div>
            </div>
          </div>

          {item.error && (
            <p className="mt-2 flex items-start gap-1.5 text-sm text-danger">
              <AlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              {item.error}
            </p>
          )}

          {item.retry_count > 0 && (
            <p className="mt-1 text-xs text-muted">Retries: {item.retry_count}</p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {isActive && (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => onPause(item.id)}
                className="gap-1.5"
              >
                <Pause className="size-3.5" aria-hidden />
                Pause
              </Button>
            )}
            {(item.status === "paused" || item.status === "failed") && (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => onResume(item.id)}
                className="gap-1.5"
              >
                <Play className="size-3.5" aria-hidden />
                Resume
              </Button>
            )}
            {item.status === "failed" && (
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => onRetry(item.id)}
                className="gap-1.5"
              >
                <RotateCcw className="size-3.5" aria-hidden />
                Retry
              </Button>
            )}
            {item.status !== "completed" && item.status !== "cancelled" && (
              <Button
                variant="ghost"
                size="sm"
                disabled={busy}
                onClick={() => onCancel(item.id)}
                className="gap-1.5 text-muted hover:text-danger"
              >
                <X className="size-3.5" aria-hidden />
                Cancel
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CompletedRow({ item }: { item: DownloadItem }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border/30 bg-white/[0.02] px-4 py-3 transition-colors hover:border-emerald-500/20">
      <DownloadThumbnail title={item.series_title} />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-fg">{item.series_title}</p>
        <p className="truncate text-sm text-muted">
          {item.chapter_title} · {formatBytes(item.bytes_downloaded)}
        </p>
      </div>
      <CheckCircle2 className="size-5 shrink-0 text-success" aria-label="Completed" />
    </div>
  );
}

function SeriesGroupCard({
  group,
  filter,
  busy,
  onPauseSeries,
  onResumeSeries,
  onCancelSeries,
  onPauseItem,
  onResumeItem,
  onCancelItem,
  onRetryItem,
}: {
  group: SeriesDownloadGroup;
  filter: FilterTab;
  busy: boolean;
  onPauseSeries: () => void;
  onResumeSeries: () => void;
  onCancelSeries: () => void;
  onPauseItem: (id: number) => void;
  onResumeItem: (id: number) => void;
  onCancelItem: (id: number) => void;
  onRetryItem: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(true);
  const rows = visibleGroupItems(group).filter((item) => matchesFilter(item, filter));

  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="space-y-3">
      <div className="glass-panel flex flex-wrap items-start justify-between gap-3 rounded-xl px-4 py-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            className="flex items-center gap-2 text-left"
          >
            <h3 className="font-semibold text-fg">{group.series_title}</h3>
            {expanded ? (
              <ChevronUp className="size-4 text-muted" aria-hidden />
            ) : (
              <ChevronDown className="size-4 text-muted" aria-hidden />
            )}
          </button>
          <p className="mt-1 text-xs text-muted">
            {group.source} · {rows.length} chapter{rows.length === 1 ? "" : "s"} in queue
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {group.active > 0 && (
              <Badge variant="primary" className="capitalize">
                {group.active} downloading
              </Badge>
            )}
            {group.queued > 0 && (
              <Badge variant="default" className="border-cyan-500/30 text-cyan-400">
                {group.queued} queued
              </Badge>
            )}
            {group.paused > 0 && (
              <Badge variant="warning">{group.paused} paused</Badge>
            )}
            {group.failed > 0 && (
              <Badge variant="warning">{group.failed} failed</Badge>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={busy || !seriesCanPause(group)}
            onClick={onPauseSeries}
          >
            Pause Series
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={busy || !seriesCanResume(group)}
            onClick={onResumeSeries}
          >
            Resume Series
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={busy || !seriesCanCancel(group)}
            onClick={onCancelSeries}
            className="text-muted hover:text-danger"
          >
            Cancel Series
          </Button>
        </div>
      </div>

      {expanded && (
        <div className="space-y-3 pl-0 sm:pl-2">
          {rows.map((item) => (
            <DownloadRow
              key={item.id}
              item={item}
              busy={busy}
              onPause={onPauseItem}
              onResume={onResumeItem}
              onCancel={onCancelItem}
              onRetry={onRetryItem}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function DownloadsSkeleton() {
  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10" aria-busy="true" aria-label="Loading downloads">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 h-10 w-48 animate-pulse rounded-lg bg-surface-2" />
        <div className="mb-6 h-28 animate-pulse rounded-xl bg-surface-2" />
        <div className="mb-6 flex gap-2">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-9 w-28 animate-pulse rounded-full bg-surface-2" />
          ))}
        </div>
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-36 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function DownloadsView() {
  const downloadsQuery = useDownloads();
  const metricsQuery = useDownloadMetrics();
  const pauseMutation = usePauseDownload();
  const resumeMutation = useResumeDownload();
  const cancelMutation = useCancelDownload();
  const retryMutation = useRetryDownload();
  const pauseSeriesMutation = usePauseSeries();
  const resumeSeriesMutation = useResumeSeries();
  const cancelSeriesMutation = useCancelSeries();
  const pauseAllMutation = usePauseAllDownloads();
  const resumeAllMutation = useResumeAllDownloads();
  const cancelAllMutation = useCancelAllDownloads();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [filterTab, setFilterTab] = useState<FilterTab>("all");
  const [completedOpen, setCompletedOpen] = useState(true);

  const busy =
    pauseMutation.isPending ||
    resumeMutation.isPending ||
    cancelMutation.isPending ||
    retryMutation.isPending ||
    pauseSeriesMutation.isPending ||
    resumeSeriesMutation.isPending ||
    cancelSeriesMutation.isPending ||
    pauseAllMutation.isPending ||
    resumeAllMutation.isPending ||
    cancelAllMutation.isPending;

  const items = useMemo(() => downloadsQuery.data ?? [], [downloadsQuery.data]);
  const metrics = metricsQuery.data;

  const queueItems = useMemo(
    () => items.filter((item) => !HIDDEN_FROM_QUEUE.has(item.status)),
    [items],
  );

  const completedItems = useMemo(
    () => items.filter((item) => item.status === "completed"),
    [items],
  );

  const groups = useMemo(
    () =>
      groupDownloadsBySeries(items).filter(
        (group) => visibleGroupItems(group).some((item) => matchesFilter(item, filterTab)),
      ),
    [items, filterTab],
  );

  const overallPercent = metrics && metrics.total > 0
    ? Math.round((metrics.completed / metrics.total) * 100)
    : 0;

  if (downloadsQuery.isLoading) {
    return <DownloadsSkeleton />;
  }

  if (downloadsQuery.error) {
    const message =
      downloadsQuery.error instanceof ApiError
        ? downloadsQuery.error.message
        : "Failed to load downloads.";
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-4 p-6 text-center">
        <div className="flex size-14 items-center justify-center rounded-full bg-danger/10">
          <AlertCircle className="size-7 text-danger" />
        </div>
        <p className="text-danger">{message}</p>
        <Button variant="secondary" onClick={() => downloadsQuery.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  const runBulk = async (
    action: () => Promise<{ affected: number }>,
    label: string,
  ) => {
    setFeedback(null);
    try {
      const result = await action();
      setFeedback(`${label}: ${result.affected} chapter${result.affected === 1 ? "" : "s"} affected.`);
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : `Failed to ${label.toLowerCase()}.`);
    }
  };

  const runItem = async (action: () => Promise<unknown>, label: string) => {
    setFeedback(null);
    try {
      await action();
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : `Failed to ${label.toLowerCase()}.`);
    }
  };

  const hasQueueWork = queueItems.length > 0;

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="font-display text-4xl tracking-wide text-fg">Downloads</h1>
            <p className="mt-1 text-sm text-muted">
              {metrics
                ? `${metrics.active + metrics.queued + metrics.paused} active, ${metrics.completed} completed`
                : "Queue chapters from any source connector."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={busy || items.length === 0}
              onClick={() => runBulk(() => pauseAllMutation.mutateAsync(), "Pause all")}
              className="gap-1.5"
            >
              <Pause className="size-3.5" aria-hidden />
              Pause All
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={busy || items.length === 0}
              onClick={() => runBulk(() => resumeAllMutation.mutateAsync(), "Resume all")}
              className="gap-1.5"
            >
              <Play className="size-3.5" aria-hidden />
              Resume All
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy || items.length === 0}
              onClick={() => runBulk(() => cancelAllMutation.mutateAsync(), "Cancel all")}
              className="gap-1.5 text-muted hover:text-danger"
            >
              <X className="size-3.5" aria-hidden />
              Cancel All
            </Button>
          </div>
        </div>

        {metrics && (
          <div className="glass-panel mb-6 rounded-2xl p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/20 to-cyan-500/10 text-violet-400">
                  <Download className="size-5" />
                </div>
                <div>
                  <p className="font-medium text-fg">Overall Progress</p>
                  <p className="text-sm text-muted">
                    {metrics.active} downloading, {metrics.queued} queued
                    {metrics.paused > 0 ? `, ${metrics.paused} paused` : ""}
                  </p>
                </div>
              </div>
              <p className="font-display text-3xl tabular-nums text-fg">{overallPercent}%</p>
            </div>
            <GradientProgress
              value={overallPercent}
              className="mt-4 h-2.5"
              aria-label="Overall download progress"
            />
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              <StatTile label="Active" value={String(metrics.active)} accent="violet" />
              <StatTile label="Queued" value={String(metrics.queued)} accent="cyan" />
              <StatTile label="Completed" value={String(metrics.completed)} accent="emerald" />
              <StatTile label="Failed" value={String(metrics.failed)} accent="amber" />
              <StatTile
                label="Speed"
                value={formatSpeed(metrics.overall_speed_bps, metrics.overall_speed_mbps)}
                icon={Zap}
                accent="cyan"
              />
              <StatTile
                label="ETA"
                value={formatEta(metrics.overall_eta_seconds)}
                icon={Gauge}
                accent="violet"
              />
            </div>
          </div>
        )}

        {feedback && (
          <p className="mb-4 rounded-lg border border-border/50 bg-surface-2/50 px-4 py-2 text-sm text-muted">
            {feedback}
          </p>
        )}

        {hasQueueWork && (
          <div className="mb-6 flex flex-wrap gap-2">
            <FilterChip
              label="All Active"
              count={filterCount(items, "all")}
              active={filterTab === "all"}
              onClick={() => setFilterTab("all")}
            />
            <FilterChip
              label="Downloading"
              count={filterCount(items, "downloading")}
              active={filterTab === "downloading"}
              onClick={() => setFilterTab("downloading")}
              tone="violet"
            />
            <FilterChip
              label="Queued"
              count={filterCount(items, "queued")}
              active={filterTab === "queued"}
              onClick={() => setFilterTab("queued")}
              tone="cyan"
            />
            <FilterChip
              label="Paused"
              count={filterCount(items, "paused")}
              active={filterTab === "paused"}
              onClick={() => setFilterTab("paused")}
              tone="amber"
            />
            <FilterChip
              label="Error"
              count={filterCount(items, "failed")}
              active={filterTab === "failed"}
              onClick={() => setFilterTab("failed")}
              tone="danger"
            />
          </div>
        )}

        {!hasQueueWork && completedItems.length === 0 ? (
          <div className="glass-panel rounded-2xl border border-dashed border-border/50 p-12 text-center">
            <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-violet-500/10">
              <Download className="size-8 text-violet-400" />
            </div>
            <p className="text-lg font-medium text-fg">No downloads yet</p>
            <p className="mx-auto mt-2 max-w-md text-sm text-muted">
              Browse a source and queue chapters from a series page. Completed downloads import
              into your local library automatically.
            </p>
          </div>
        ) : !hasQueueWork && completedItems.length > 0 ? (
          <div className="glass-panel mb-6 rounded-2xl border border-dashed border-border/50 p-8 text-center">
            <p className="font-medium text-fg">All caught up</p>
            <p className="mt-2 text-sm text-muted">
              Completed chapters are in your library; cancelled ones were removed from this view.
            </p>
          </div>
        ) : groups.length === 0 ? (
          <div className="glass-panel mb-6 rounded-2xl border border-dashed border-border/50 p-8 text-center">
            <p className="font-medium text-fg">No downloads match this filter</p>
            <p className="mt-2 text-sm text-muted">Try another status tab to see active queue items.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {groups.map((group) => (
              <SeriesGroupCard
                key={group.key}
                group={group}
                filter={filterTab}
                busy={busy}
                onPauseSeries={() =>
                  runBulk(
                    () =>
                      pauseSeriesMutation.mutateAsync({
                        source_id: group.source,
                        series_id: group.series_id,
                      }),
                    `Pause ${group.series_title}`,
                  )
                }
                onResumeSeries={() =>
                  runBulk(
                    () =>
                      resumeSeriesMutation.mutateAsync({
                        source_id: group.source,
                        series_id: group.series_id,
                      }),
                    `Resume ${group.series_title}`,
                  )
                }
                onCancelSeries={() =>
                  runBulk(
                    () =>
                      cancelSeriesMutation.mutateAsync({
                        source_id: group.source,
                        series_id: group.series_id,
                      }),
                    `Cancel ${group.series_title}`,
                  )
                }
                onPauseItem={(id) => runItem(() => pauseMutation.mutateAsync(id), "Pause chapter")}
                onResumeItem={(id) => runItem(() => resumeMutation.mutateAsync(id), "Resume chapter")}
                onCancelItem={(id) => runItem(() => cancelMutation.mutateAsync(id), "Cancel chapter")}
                onRetryItem={(id) => runItem(() => retryMutation.mutateAsync(id), "Retry chapter")}
              />
            ))}
          </div>
        )}

        {completedItems.length > 0 && (
          <section className="mt-8">
            <button
              type="button"
              onClick={() => setCompletedOpen((open) => !open)}
              className="mb-4 flex w-full items-center justify-between gap-3 rounded-xl px-1 py-1 text-left transition-colors hover:text-violet-400"
            >
              <span className="inline-flex items-center gap-2 font-medium text-fg">
                <CheckCircle2 className="size-4 text-success" aria-hidden />
                Completed ({completedItems.length})
              </span>
              {completedOpen ? (
                <ChevronUp className="size-4 text-muted" aria-hidden />
              ) : (
                <ChevronDown className="size-4 text-muted" aria-hidden />
              )}
            </button>
            {completedOpen && (
              <div className="space-y-2">
                {completedItems.map((item) => (
                  <CompletedRow key={item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
