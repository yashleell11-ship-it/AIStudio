"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  Gauge,
  Pause,
  Play,
  RotateCcw,
  TriangleAlert,
  X,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import {
  canCancelDownload,
  canMoveDownload,
  canPauseDownload,
  canResumeDownload,
  canRetryDownload,
  describeDownloadStatus,
  groupDownloadsBySeries,
  seriesCanCancel,
  seriesCanPause,
  seriesCanResume,
  summarizeFailures,
  visibleGroupItems,
  type DownloadStatusTone,
} from "../grouping";
import {
  useCancelAllDownloads,
  useCancelDownload,
  useCancelSeries,
  useDownloadMetrics,
  useDownloads,
  useMoveDownload,
  usePauseAllDownloads,
  usePauseDownload,
  usePauseSeries,
  useResumeAllDownloads,
  useResumeDownload,
  useResumeSeries,
  useRetryDownload,
  useRetryFailedDownloads,
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

// One colour per queue state, keyed off the shared descriptor rather than the
// raw string, so the badge, the filter chip, and the metrics tile can never
// disagree about what "failed" is called or what colour it is.
const TONE_BADGE_CLASS: Record<DownloadStatusTone, string> = {
  active: "border-primary/40 bg-primary/15 text-primary",
  pending: "border-accent/40 bg-accent/15 text-accent",
  paused: "border-warning/40 bg-warning/15 text-warning",
  failed: "border-danger/40 bg-danger/15 text-danger",
  done: "border-success/40 bg-success/15 text-success",
  neutral: "border-border bg-surface-2 text-muted",
};

function StatusBadge({ status }: { status: string }) {
  const descriptor = describeDownloadStatus(status);
  return (
    <span
      title={descriptor.description}
      className={cn(
        "inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
        TONE_BADGE_CLASS[descriptor.tone],
      )}
    >
      {descriptor.tone === "active" && (
        <span className="mr-1.5 size-1.5 animate-pulse rounded-full bg-primary" />
      )}
      {descriptor.label}
    </span>
  );
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
        className="h-full rounded-full bg-gradient-to-r from-accent to-primary transition-all duration-500 ease-out"
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

function StatTile({
  label,
  value,
  icon: Icon,
  accent = "amber",
}: {
  label: string;
  value: string;
  icon?: React.ComponentType<{ className?: string }>;
  accent?: "amber" | "rose" | "success" | "warning" | "danger";
}) {
  const accentStyles = {
    amber: "from-primary/20 to-primary/5 text-primary",
    rose: "from-accent/20 to-accent/5 text-accent",
    success: "from-success/20 to-success/5 text-success",
    warning: "from-warning/20 to-warning/5 text-warning",
    danger: "from-danger/20 to-danger/5 text-danger",
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
    <div className="relative flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-primary/30 to-accent/20 ring-1 ring-white/10">
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
  tone = "amber",
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
  tone?: "amber" | "rose" | "warning" | "danger";
}) {
  const toneActive = {
    amber: "border-primary/50 bg-primary/20 text-primary",
    rose: "border-accent/50 bg-accent/20 text-accent",
    warning: "border-warning/50 bg-warning/20 text-warning",
    danger: "border-danger/50 bg-danger/20 text-danger",
  };
  const toneIdle = {
    amber: "hover:border-primary/30 hover:text-primary",
    rose: "hover:border-accent/30 hover:text-accent",
    warning: "hover:border-warning/30 hover:text-warning",
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

interface RowActions {
  onPause: (id: number) => void;
  onResume: (id: number) => void;
  onCancel: (id: number) => void;
  onRetry: (id: number) => void;
  onMove: (id: number, direction: "up" | "down") => void;
}

function DownloadRow({
  item,
  onPause,
  onResume,
  onCancel,
  onRetry,
  onMove,
  busy,
}: RowActions & {
  item: DownloadItem;
  busy: boolean;
}) {
  const descriptor = describeDownloadStatus(item.status);

  return (
    <div className="glass-card rounded-xl p-4 transition-colors hover:border-primary/30">
      <div className="flex gap-4">
        <DownloadThumbnail title={item.series_title} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate font-medium text-fg">{item.series_title}</p>
              <p className="mt-0.5 truncate text-sm text-muted">{item.chapter_title}</p>
            </div>
            <StatusBadge status={item.status} />
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
                  <span className="inline-flex items-center gap-1 text-primary">
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

          {item.error ? (
            <div className="mt-2 rounded-lg border border-danger/25 bg-danger/5 p-2.5">
              <p className="flex items-start gap-1.5 text-xs font-semibold uppercase tracking-wider text-danger">
                <AlertCircle className="mt-px size-3.5 shrink-0" aria-hidden />
                Error reported by the server
              </p>
              {/* Wrapped, not truncated: this string is the only explanation
                  the owner gets for why the chapter stopped. */}
              <p className="mt-1 break-words font-mono text-xs leading-relaxed text-danger">
                {item.error}
              </p>
            </div>
          ) : (
            <p className="mt-2 text-xs text-muted">{descriptor.description}</p>
          )}

          {item.retry_count > 0 && (
            <p className="mt-1 text-xs text-muted">
              Retried {item.retry_count} time{item.retry_count === 1 ? "" : "s"} already.
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {canPauseDownload(item) && (
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
            {canRetryDownload(item) && (
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
            {/* Resume and retry both re-queue the chapter; retry additionally
                bumps `retry_count`, so it is the one offered for a failure and
                this stays for a chapter the user paused deliberately. */}
            {canResumeDownload(item) && item.status === "paused" && (
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
            {canCancelDownload(item) && (
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
            {canMoveDownload(item) && (
              <span className="ml-auto inline-flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={busy}
                  aria-label={`Move ${item.chapter_title} earlier in the queue`}
                  onClick={() => onMove(item.id, "up")}
                >
                  <ArrowUp className="size-3.5" aria-hidden />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={busy}
                  aria-label={`Move ${item.chapter_title} later in the queue`}
                  onClick={() => onMove(item.id, "down")}
                >
                  <ArrowDown className="size-3.5" aria-hidden />
                </Button>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function CompletedRow({ item }: { item: DownloadItem }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border/30 bg-white/[0.02] px-4 py-3 transition-colors hover:border-success/20">
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

/**
 * Everything that failed, pulled out of the per-series accordions and put at
 * the top of the page.
 *
 * A failed chapter never retries itself, so it is the only queue state that
 * needs the owner. Buried inside a collapsed series group — behind a filter tab
 * they have to know to click — is exactly how forty dead chapters go unnoticed.
 */
function FailuresPanel({
  items,
  busy,
  onRetryAll,
  onRetry,
  onCancel,
}: {
  items: DownloadItem[];
  busy: boolean;
  onRetryAll: (ids: number[]) => void;
  onRetry: (id: number) => void;
  onCancel: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const summary = useMemo(() => summarizeFailures(items), [items]);

  if (summary.count === 0) {
    return null;
  }

  return (
    <section className="mb-6 rounded-2xl border border-danger/30 bg-danger/[0.07] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-danger/15 text-danger">
            <TriangleAlert className="size-5" aria-hidden />
          </span>
          <div className="min-w-0">
            <h2 className="font-semibold text-fg">
              {summary.count} chapter{summary.count === 1 ? "" : "s"} failed
            </h2>
            <p className="mt-0.5 text-sm text-muted">
              Across {summary.seriesCount} series. Failed downloads do not retry on their own.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            disabled={busy || summary.retriableIds.length === 0}
            onClick={() => onRetryAll(summary.retriableIds)}
            className="gap-1.5"
          >
            <RotateCcw className="size-3.5" aria-hidden />
            Retry all {summary.retriableIds.length}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setExpanded((value) => !value)}
            className="gap-1.5"
          >
            {expanded ? (
              <>
                <ChevronUp className="size-3.5" aria-hidden />
                Hide chapters
              </>
            ) : (
              <>
                <ChevronDown className="size-3.5" aria-hidden />
                Show chapters
              </>
            )}
          </Button>
        </div>
      </div>

      {/* One line per distinct error: a dead connector fails every chapter with
          the same string, and forty copies of it is not a report. */}
      <ul className="mt-4 space-y-2">
        {summary.reasons.map((reason) => (
          <li key={reason.message} className="flex items-start gap-2">
            <Badge className="shrink-0 border-danger/30 bg-danger/15 text-danger">
              {reason.count}×
            </Badge>
            <span className="min-w-0 break-words font-mono text-xs leading-relaxed text-fg">
              {reason.message}
            </span>
          </li>
        ))}
      </ul>

      {expanded && (
        <ul className="mt-4 space-y-2">
          {summary.items.map((item) => (
            <li
              key={item.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border/40 bg-black/10 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-fg">
                  {item.series_title}
                  <span className="text-muted"> · {item.chapter_title}</span>
                </p>
                <p className="text-xs text-muted">
                  {item.source} · failed {formatBytes(item.bytes_downloaded)} in ·{" "}
                  {item.retry_count} previous retr{item.retry_count === 1 ? "y" : "ies"}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={() => onRetry(item.id)}
                  className="gap-1.5"
                >
                  <RotateCcw className="size-3.5" aria-hidden />
                  Retry
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => onCancel(item.id)}
                  className="gap-1.5 text-muted hover:text-danger"
                >
                  <X className="size-3.5" aria-hidden />
                  Cancel
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
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
  onMoveItem,
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
  onMoveItem: (id: number, direction: "up" | "down") => void;
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
              <Badge variant="default" className="border-accent/30 text-accent">
                {group.queued} queued
              </Badge>
            )}
            {group.paused > 0 && (
              <Badge variant="warning">{group.paused} paused</Badge>
            )}
            {/* Failed is danger, not warning: "paused" is a choice the owner
                made and "failed" is not, so they must not read alike. */}
            {group.failed > 0 && (
              <Badge className="border-danger/30 bg-danger/15 text-danger">
                {group.failed} failed
              </Badge>
            )}
            {group.completed > 0 && (
              <Badge variant="success">{group.completed} completed</Badge>
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
              onMove={onMoveItem}
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
  const moveMutation = useMoveDownload();
  const retryFailedMutation = useRetryFailedDownloads();
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
    cancelAllMutation.isPending ||
    moveMutation.isPending ||
    retryFailedMutation.isPending;

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

  // Reports what the loop actually achieved. A retry the server refuses (a row
  // that is no longer failed, say) must not be reported as success, and must
  // not stop the remaining chapters from being retried either.
  const retryAllFailed = async (ids: number[]) => {
    setFeedback(null);
    try {
      const result = await retryFailedMutation.mutateAsync(ids);
      setFeedback(
        result.rejected.length === 0
          ? `Re-queued ${result.retried} chapter${result.retried === 1 ? "" : "s"}.`
          : `Re-queued ${result.retried} of ${result.requested}. ${result.rejected.length} refused: ${result.rejected[0].message}`,
      );
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to retry downloads.");
    }
  };

  const hasQueueWork = queueItems.length > 0;

  return (
    <div className="min-h-full bg-bg px-6 py-6 md:px-10">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <HeroHeading className="text-[clamp(1.75rem,9vw,2.75rem)] leading-none md:text-6xl">
              Downloads
            </HeroHeading>
            <p className="mt-2 text-sm text-muted">
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
                <div className="flex size-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
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
              <StatTile label="Active" value={String(metrics.active)} accent="amber" />
              <StatTile label="Queued" value={String(metrics.queued)} accent="rose" />
              <StatTile label="Completed" value={String(metrics.completed)} accent="success" />
              <StatTile label="Failed" value={String(metrics.failed)} accent="danger" />
              <StatTile
                label="Speed"
                value={formatSpeed(metrics.overall_speed_bps, metrics.overall_speed_mbps)}
                icon={Zap}
                accent="amber"
              />
              <StatTile
                label="ETA"
                value={formatEta(metrics.overall_eta_seconds)}
                icon={Gauge}
                accent="rose"
              />
            </div>
            {/* GET /downloads/metrics counts Download rows across every account
                (backend/services/download_manager.py:201-207) while the list
                below is filtered to this account, so on a shared instance the
                two legitimately disagree. Say so rather than let it read as a
                bug. */}
            <p className="mt-3 text-xs text-muted">
              Totals cover every account on this server. The queue below is yours.
            </p>
          </div>
        )}

        {feedback && (
          <p className="mb-4 rounded-lg border border-border/50 bg-surface-2/50 px-4 py-2 text-sm text-muted">
            {feedback}
          </p>
        )}

        <FailuresPanel
          items={items}
          busy={busy}
          onRetryAll={retryAllFailed}
          onRetry={(id) => runItem(() => retryMutation.mutateAsync(id), "Retry chapter")}
          onCancel={(id) => runItem(() => cancelMutation.mutateAsync(id), "Cancel chapter")}
        />

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
              tone="amber"
            />
            <FilterChip
              label="Queued"
              count={filterCount(items, "queued")}
              active={filterTab === "queued"}
              onClick={() => setFilterTab("queued")}
              tone="rose"
            />
            <FilterChip
              label="Paused"
              count={filterCount(items, "paused")}
              active={filterTab === "paused"}
              onClick={() => setFilterTab("paused")}
              tone="warning"
            />
            <FilterChip
              label="Failed"
              count={filterCount(items, "failed")}
              active={filterTab === "failed"}
              onClick={() => setFilterTab("failed")}
              tone="danger"
            />
          </div>
        )}

        {!hasQueueWork && completedItems.length === 0 ? (
          <div className="glass-panel rounded-2xl border border-dashed border-border/50 p-12 text-center">
            <div className="mx-auto mb-4 flex size-16 items-center justify-center rounded-full bg-primary/10">
              <Download className="size-8 text-primary" />
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
                onMoveItem={(downloadId, direction) =>
                  runItem(
                    () => moveMutation.mutateAsync({ downloadId, direction }),
                    "Reorder chapter",
                  )
                }
              />
            ))}
          </div>
        )}

        {completedItems.length > 0 && (
          <section className="mt-8">
            <button
              type="button"
              onClick={() => setCompletedOpen((open) => !open)}
              className="mb-4 flex w-full items-center justify-between gap-3 rounded-xl px-1 py-1 text-left transition-colors hover:text-primary"
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
