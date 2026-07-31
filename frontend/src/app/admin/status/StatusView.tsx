"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock,
  Download,
  HardDrive,
  RefreshCw,
  Server,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FadeIn } from "@/components/premium/FadeIn";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { useCurrentUser } from "@/features/auth/hooks";
import { useDownloadMetrics, useDownloads } from "@/features/downloads/hooks";
import { describeCheckSchedule } from "@/features/updates/notifications";
import {
  useManualCheck,
  useTrackers,
  useUpdateRuns,
  useUpdateSettings,
  useUpdateSources,
} from "@/features/updates/hooks";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useBackendHealth } from "./hooks";
import {
  deriveBackendHealth,
  deriveCheckerHealth,
  deriveQueueHealth,
  deriveSourceHealth,
  deriveSystemSummary,
  instanceWideTotals,
  worstState,
  type HealthState,
} from "./status";

function formatWhen(value: string | null | undefined): string {
  if (!value) return "Never";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "Unknown";
  return new Date(parsed).toLocaleString();
}

function formatRelative(value: string | null | undefined, nowMs: number): string | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return null;
  const deltaMinutes = Math.round((nowMs - parsed) / 60_000);
  const magnitude = Math.abs(deltaMinutes);
  const unit =
    magnitude < 60
      ? `${magnitude} min`
      : magnitude < 60 * 24
        ? `${Math.round(magnitude / 60)} h`
        : `${Math.round(magnitude / (60 * 24))} d`;
  return deltaMinutes >= 0 ? `${unit} ago` : `in ${unit}`;
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

const STATE_STYLES: Record<
  HealthState,
  { dot: string; text: string; ring: string; label: string }
> = {
  ok: {
    dot: "bg-success",
    text: "text-success",
    ring: "border-success/30 bg-success/10",
    label: "Healthy",
  },
  warn: {
    dot: "bg-warning",
    text: "text-warning",
    ring: "border-warning/30 bg-warning/10",
    label: "Warning",
  },
  down: {
    dot: "bg-danger",
    text: "text-danger",
    ring: "border-danger/30 bg-danger/10",
    label: "Down",
  },
  unknown: {
    dot: "bg-muted",
    text: "text-muted",
    ring: "border-border/50 bg-white/[0.02]",
    label: "Unknown",
  },
};

function StateIcon({ state, className }: { state: HealthState; className?: string }) {
  const Icon =
    state === "ok"
      ? CheckCircle2
      : state === "warn"
        ? TriangleAlert
        : state === "down"
          ? AlertCircle
          : CircleHelp;
  return <Icon className={cn("size-4 shrink-0", STATE_STYLES[state].text, className)} aria-hidden />;
}

function StatePill({ state, label }: { state: HealthState; label?: string }) {
  const styles = STATE_STYLES[state];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        styles.ring,
        styles.text,
      )}
    >
      <span className={cn("size-1.5 rounded-full", styles.dot)} aria-hidden />
      {label ?? styles.label}
    </span>
  );
}

function StatusCard({
  title,
  state,
  icon: Icon,
  children,
  action,
}: {
  title: string;
  state: HealthState;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 p-4 pb-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-lg border",
              STATE_STYLES[state].ring,
              STATE_STYLES[state].text,
            )}
          >
            <Icon className="size-4" aria-hidden />
          </span>
          <CardTitle className="truncate">{title}</CardTitle>
        </div>
        <div className="flex items-center gap-2">
          {action}
          <StatePill state={state} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-0 text-sm">{children}</CardContent>
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/30 py-1.5 last:border-b-0">
      <span className="shrink-0 text-xs uppercase tracking-wider text-muted">{label}</span>
      <span className="min-w-0 truncate text-right text-fg">{value}</span>
    </div>
  );
}

/**
 * A message the backend produced (an error string, a connector traceback tail).
 * Wrapped and scrollable rather than truncated: the whole point of this page is
 * that the owner gets to read the actual failure.
 */
function ServerMessage({ children }: { children: React.ReactNode }) {
  return (
    <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-danger/20 bg-danger/5 p-3 font-mono text-xs leading-relaxed text-danger">
      {children}
    </pre>
  );
}

function EmptyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border/50 px-3 py-2.5 text-xs leading-relaxed text-muted">
      {children}
    </p>
  );
}

export function StatusView() {
  const { data: user, isLoading: userLoading } = useCurrentUser();
  // A single clock for the whole render, so "last run" and "next run" cannot
  // disagree by the milliseconds between two Date.now() calls.
  const [nowMs, setNowMs] = useState(() => Date.now());

  const health = useBackendHealth();
  const settings = useUpdateSettings();
  const runs = useUpdateRuns();
  const trackers = useTrackers();
  const downloads = useDownloads();
  const metrics = useDownloadMetrics();
  const manualCheck = useManualCheck();
  const sources = useUpdateSources();

  const schedule = useMemo(
    () => describeCheckSchedule(settings.data, nowMs),
    [settings.data, nowMs],
  );

  const backendHealth = useMemo(
    () =>
      deriveBackendHealth({
        status: health.data,
        error: health.error,
        isLoading: health.isLoading,
      }),
    [health.data, health.error, health.isLoading],
  );

  const checkerHealth = useMemo(
    () =>
      deriveCheckerHealth({
        settings: settings.data,
        runs: runs.data,
        schedule,
        isLoading: settings.isLoading || runs.isLoading,
      }),
    [settings.data, settings.isLoading, runs.data, runs.isLoading, schedule],
  );

  const sourceHealth = useMemo(
    () => deriveSourceHealth(trackers.data, sources.data),
    [trackers.data, sources.data],
  );

  const queueHealth = useMemo(
    () => deriveQueueHealth(downloads.data, downloads.isLoading),
    [downloads.data, downloads.isLoading],
  );

  const totals = instanceWideTotals(metrics.data);

  const summary = useMemo(
    () =>
      deriveSystemSummary({
        backend: backendHealth,
        checker: checkerHealth,
        sources: sourceHealth,
        queue: queueHealth,
      }),
    [backendHealth, checkerHealth, sourceHealth, queueHealth],
  );

  const refreshAll = () => {
    setNowMs(Date.now());
    void health.refetch();
    void settings.refetch();
    void runs.refetch();
    void trackers.refetch();
    void downloads.refetch();
    void metrics.refetch();
    void sources.refetch();
  };

  if (userLoading) {
    return (
      <div className="page-shell">
        <div className="page-container mx-auto max-w-5xl" aria-busy="true">
          <div className="h-12 w-64 animate-pulse rounded-lg bg-surface-2" />
        </div>
      </div>
    );
  }

  // The API distinguishes admins (`is_admin` on GET /auth/me, set on the first
  // account created), and this page reports instance-wide health, so it is
  // gated on that flag rather than on merely being signed in.
  if (!user?.is_admin) {
    return (
      <div className="page-shell">
        <div className="page-container mx-auto max-w-2xl">
          <Card>
            <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
              <ShieldAlert className="size-8 text-warning" aria-hidden />
              <h1 className="text-lg font-semibold text-fg">Administrators only</h1>
              <p className="max-w-sm text-sm text-muted">
                System status is instance-wide configuration and health. Ask the account owner
                to check it for you.
              </p>
              <Link href="/" className="text-sm text-primary hover:underline">
                Back to home
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  const anyRefreshing =
    health.isFetching ||
    settings.isFetching ||
    runs.isFetching ||
    trackers.isFetching ||
    downloads.isFetching;

  return (
    <div className="page-shell">
      <div className="page-container mx-auto max-w-5xl space-y-6">
        <FadeIn y={20}>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">
                Administration
              </p>
              <HeroHeading className="text-[clamp(1.75rem,9vw,2.75rem)] leading-none md:text-6xl">
                System Status
              </HeroHeading>
              <p className="mt-3 max-w-xl text-sm text-muted">
                Backend health, the update checker, per-source failures, and the download
                queue — everything that can break quietly.
              </p>
            </div>
            <Button
              variant="secondary"
              onClick={refreshAll}
              disabled={anyRefreshing}
              className="gap-2"
            >
              <RefreshCw className={cn("size-4", anyRefreshing && "animate-spin")} aria-hidden />
              {anyRefreshing ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
        </FadeIn>

        <FadeIn y={20} delay={0.05}>
          <div
            className={cn(
              "rounded-2xl border p-5",
              STATE_STYLES[summary.state].ring,
            )}
          >
            <div className="flex flex-wrap items-center gap-3">
              <StateIcon state={summary.state} className="size-5" />
              <p className={cn("font-display text-xl tracking-wide", STATE_STYLES[summary.state].text)}>
                {summary.headline}
              </p>
            </div>
            {summary.problems.length > 0 ? (
              <ul className="mt-3 space-y-1.5 text-sm text-fg">
                {summary.problems.map((problem, index) => (
                  <li key={index} className="flex gap-2">
                    <span className="text-muted" aria-hidden>
                      •
                    </span>
                    <span className="min-w-0">{problem}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </FadeIn>

        <FadeIn y={20} delay={0.1}>
          <div className="grid gap-4 lg:grid-cols-2">
            <StatusCard title="Backend" state={backendHealth.state} icon={Server}>
              <p className="text-muted">{backendHealth.message}</p>
              <div>
                <Fact label="Name" value={backendHealth.name ?? "—"} />
                <Fact
                  label="Version"
                  value={
                    backendHealth.version ? (
                      <span className="font-mono">{backendHealth.version}</span>
                    ) : (
                      "—"
                    )
                  }
                />
                <Fact label="Probe" value={<span className="font-mono">GET /health</span>} />
              </div>
            </StatusCard>

            <StatusCard
              title="Update checker"
              state={checkerHealth.state}
              icon={Clock}
              action={
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={manualCheck.isPending}
                  onClick={() => manualCheck.mutate({})}
                >
                  {manualCheck.isPending ? "Starting…" : "Check now"}
                </Button>
              }
            >
              <p className="text-muted">{checkerHealth.message}</p>
              <div>
                <Fact
                  label="Last run"
                  value={
                    <>
                      {formatWhen(schedule?.lastRunAt)}
                      {formatRelative(schedule?.lastRunAt, nowMs) ? (
                        <span className="text-muted">
                          {" "}
                          ({formatRelative(schedule?.lastRunAt, nowMs)})
                        </span>
                      ) : null}
                    </>
                  }
                />
                <Fact
                  label="Next run (est.)"
                  value={
                    schedule?.estimatedNextRunAt ? (
                      <>
                        {formatWhen(schedule.estimatedNextRunAt)}
                        <span className="text-muted">
                          {" "}
                          ({formatRelative(schedule.estimatedNextRunAt, nowMs)})
                        </span>
                      </>
                    ) : (
                      "Unknown"
                    )
                  }
                />
                <Fact
                  label="Interval"
                  value={schedule ? `${schedule.intervalMinutes} min` : "—"}
                />
                <Fact
                  label="Failed runs (recent)"
                  value={
                    <span className={checkerHealth.failedRuns.length > 0 ? "text-danger" : undefined}>
                      {checkerHealth.failedRuns.length}
                    </span>
                  }
                />
              </div>
              {manualCheck.error instanceof ApiError ? (
                <ServerMessage>{manualCheck.error.message}</ServerMessage>
              ) : null}
              <p className="text-xs leading-relaxed text-muted">
                The next-run time is an estimate: it is the last finished run plus the interval.
                The backend exposes no scheduler timestamp of its own.
              </p>
            </StatusCard>
          </div>
        </FadeIn>

        <FadeIn y={20} delay={0.15}>
          <StatusCard
            title="Recent update checks"
            state={checkerHealth.state}
            icon={Activity}
          >
            {runs.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-6 animate-pulse rounded bg-surface-2" />
                ))}
              </div>
            ) : (runs.data ?? []).length === 0 ? (
              <EmptyNote>
                No update check has been recorded yet. Runs appear here once the scheduler has
                fired or you press “Check now”.
              </EmptyNote>
            ) : (
              <ul className="space-y-2">
                {(runs.data ?? []).slice(0, 8).map((entry) => (
                  <li
                    key={entry.id}
                    className="rounded-lg border border-border/30 bg-white/[0.02] px-3 py-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge
                          variant={
                            entry.status === "completed"
                              ? "success"
                              : entry.status === "running"
                                ? "primary"
                                : "warning"
                          }
                          className={
                            entry.status === "failed"
                              ? "border-danger/30 bg-danger/15 text-danger"
                              : undefined
                          }
                        >
                          {entry.status}
                        </Badge>
                        <span className="text-xs uppercase tracking-wider text-muted">
                          {entry.trigger}
                        </span>
                        <span className="text-sm text-fg">
                          {entry.series_checked} series · {entry.new_chapters_found} new
                        </span>
                      </div>
                      <span className="text-xs text-muted">{formatWhen(entry.started_at)}</span>
                    </div>
                    {entry.error ? <ServerMessage>{entry.error}</ServerMessage> : null}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs leading-relaxed text-muted">
              A run can finish as <span className="font-mono">completed</span> while individual
              series still failed — a connector error is recorded against the series, not the run.
              Per-source health below is where those show up.
            </p>
          </StatusCard>
        </FadeIn>

        <FadeIn y={20} delay={0.2}>
          <StatusCard
            title="Source health"
            state={
              sourceHealth.length === 0
                ? "unknown"
                : worstState(sourceHealth.map((source) => source.state))
            }
            icon={Activity}
          >
            {trackers.isLoading || sources.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-12 animate-pulse rounded bg-surface-2" />
                ))}
              </div>
            ) : sourceHealth.length === 0 ? (
              <EmptyNote>
                No sources are installed and no series is being tracked, so there is nothing to
                report.
              </EmptyNote>
            ) : (
              <ul className="space-y-2">
                {sourceHealth.map((source) => (
                  <li
                    key={source.source}
                    className="rounded-lg border border-border/30 bg-white/[0.02] px-3 py-2.5"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <StateIcon state={source.state} />
                        <span className="truncate font-medium text-fg">
                          {source.name ?? source.source}
                        </span>
                        <span className="font-mono text-xs text-muted">{source.source}</span>
                      </div>
                      <span className="text-xs text-muted">
                        {source.trackedCount} tracked · last check {formatWhen(source.lastCheckedAt)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{source.message}</p>
                    {source.lastError ? <ServerMessage>{source.lastError}</ServerMessage> : null}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs leading-relaxed text-muted">
              Derived from the last check of each followed or downloaded series, which is the
              only per-connector signal the backend records. A source with nothing tracked has no
              signal at all, and this list covers the reading profile you are viewing under.
            </p>
          </StatusCard>
        </FadeIn>

        <FadeIn y={20} delay={0.25}>
          <StatusCard
            title="Download queue"
            state={queueHealth.state}
            icon={Download}
            action={
              <Link
                href="/downloads"
                className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
              >
                Open queue
                <ChevronRight className="size-3.5" aria-hidden />
              </Link>
            }
          >
            <p className="text-muted">{queueHealth.message}</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                { label: "Downloading", value: queueHealth.active },
                { label: "Queued", value: queueHealth.queued },
                { label: "Paused", value: queueHealth.paused },
                { label: "Failed", value: queueHealth.failed },
              ].map((tile) => (
                <div
                  key={tile.label}
                  className="rounded-lg border border-border/30 bg-white/[0.02] px-3 py-2"
                >
                  <p className="text-xs text-muted">{tile.label}</p>
                  <p
                    className={cn(
                      "mt-0.5 text-lg font-semibold tabular-nums text-fg",
                      tile.label === "Failed" && tile.value > 0 && "text-danger",
                    )}
                  >
                    {tile.value}
                  </p>
                </div>
              ))}
            </div>

            {queueHealth.activeItems.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Transferring now
                </p>
                {queueHealth.activeItems.slice(0, 5).map((item) => (
                  <p key={item.id} className="truncate text-sm text-fg">
                    <span className="text-muted">{item.source} ·</span> {item.series_title} —{" "}
                    {item.chapter_title}{" "}
                    <span className="tabular-nums text-muted">
                      ({item.progress.toFixed(0)}%)
                    </span>
                  </p>
                ))}
                {queueHealth.activeItems.length > 5 ? (
                  <p className="text-xs text-muted">
                    …and {queueHealth.activeItems.length - 5} more.
                  </p>
                ) : null}
              </div>
            ) : null}

            {queueHealth.reasons.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Why chapters failed
                </p>
                {queueHealth.reasons.map((reason) => (
                  <div key={reason.message} className="flex items-start gap-2">
                    <Badge className="shrink-0 border-danger/30 bg-danger/15 text-danger">
                      {reason.count}×
                    </Badge>
                    <span className="min-w-0 break-words text-sm text-fg">{reason.message}</span>
                  </div>
                ))}
              </div>
            ) : null}

            {queueHealth.failures.length > 0 ? (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Most recent failures
                </p>
                {queueHealth.failures.slice(0, 5).map((item) => (
                  <p key={item.id} className="truncate text-sm text-fg">
                    <span className="text-muted">{item.source} ·</span> {item.series_title} —{" "}
                    {item.chapter_title}
                  </p>
                ))}
                <p className="text-xs text-muted">
                  Retry or cancel them on the{" "}
                  <Link href="/downloads" className="text-primary hover:underline">
                    downloads page
                  </Link>
                  .
                </p>
              </div>
            ) : null}

            {totals ? (
              <div>
                <Fact
                  label="Storage used"
                  value={
                    <span className="inline-flex items-center gap-1.5">
                      <HardDrive className="size-3.5 text-muted" aria-hidden />
                      {formatBytes(totals.storageUsedBytes)} used ·{" "}
                      {formatBytes(totals.storageFreeBytes)} free
                    </span>
                  }
                />
                <Fact
                  label="Workers"
                  value={`${totals.workers.running} running / ${totals.workers.active} active / ${totals.workers.configured} configured`}
                />
                <Fact
                  label="All accounts"
                  value={`${totals.total} downloads · ${totals.completed} completed · ${totals.failed} failed`}
                />
              </div>
            ) : (
              <EmptyNote>Queue metrics are still loading.</EmptyNote>
            )}
            <p className="text-xs leading-relaxed text-muted">
              The four tiles count your own queue. The “all accounts” row comes from
              <span className="font-mono"> /downloads/metrics</span>, which counts every
              account&apos;s downloads — the two are not expected to match on a shared instance.
            </p>
          </StatusCard>
        </FadeIn>

        <p className="pb-2 text-xs text-muted">
          Everything on this page is read from endpoints that already exist. Where a number is
          not exposed by the API it is shown as unknown rather than estimated.
        </p>
      </div>
    </div>
  );
}
