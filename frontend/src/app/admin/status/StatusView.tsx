"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CircleHelp,
  Clock,
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
import { describeCheckSchedule } from "@/features/updates/notifications";
import {
  useManualCheck,
  useUpdateRuns,
  useUpdateSettings,
} from "@/features/updates/hooks";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useBackendHealth, useSourceHealth } from "./hooks";
import {
  deriveBackendHealth,
  deriveCheckerHealth,
  deriveSourceHealth,
  deriveSystemSummary,
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
  const manualCheck = useManualCheck();
  const sources = useSourceHealth();

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
    () => deriveSourceHealth(sources.data),
    [sources.data],
  );

  const summary = useMemo(
    () =>
      deriveSystemSummary({
        backend: backendHealth,
        checker: checkerHealth,
        sources: sourceHealth,
      }),
    [backendHealth, checkerHealth, sourceHealth],
  );

  const refreshAll = () => {
    setNowMs(Date.now());
    void health.refetch();
    void settings.refetch();
    void runs.refetch();
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
    sources.isFetching;

  return (
    <div className="page-shell">
      <div className="page-container mx-auto max-w-5xl space-y-6">
        <FadeIn y={20}>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">
                Administration
              </p>
              <HeroHeading className="leading-none md:text-6xl">
                System Status
              </HeroHeading>
              <p className="mt-3 max-w-xl text-sm text-muted">
                Backend health, the update checker, per-source failures, and update runs
                — everything that can break quietly.
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
            {sources.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-12 animate-pulse rounded bg-surface-2" />
                ))}
              </div>
            ) : sources.isError ? (
              <ServerMessage>
                {sources.error instanceof ApiError
                  ? sources.error.message
                  : "Failed to load source health."}
              </ServerMessage>
            ) : sourceHealth.length === 0 ? (
              <EmptyNote>No sources are installed, so there is nothing to report.</EmptyNote>
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
                        {source.demoted ? (
                          <Badge className="border-warning/30 bg-warning/15 text-warning">
                            demoted
                          </Badge>
                        ) : null}
                      </div>
                      <span className="text-xs text-muted">
                        last probe {formatWhen(source.lastCheckedAt)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-muted">{source.message}</p>
                    {source.lastError ? <ServerMessage>{source.lastError}</ServerMessage> : null}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs leading-relaxed text-muted">
              Recorded by the federated-search fan-out: every installed source is probed on every
              search, and a source that stops answering is flagged here (and pushed down search
              results) rather than failing silently. Timestamps are accurate to within a few hours.
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
