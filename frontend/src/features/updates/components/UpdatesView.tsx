"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeftRight, Bell, ChevronRight, RefreshCw, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { PrimaryPillButton } from "@/components/premium/PrimaryPillButton";
import { GhostPillButton } from "@/components/premium/GhostPillButton";
import { ApiError } from "@/types/api";
import {
  useManualCheck,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useSyncDownloaded,
  useTrackers,
  useUnfollowTracker,
  useUpdateNotifications,
  useUpdateRuns,
  useUpdateSettings,
  useUpdateTracker,
} from "../hooks";
import type { SeriesTracker, UpdateNotification } from "../types";
import { MigrateSeriesDialog } from "./MigrateSeriesDialog";

function formatWhen(value: string | null): string {
  if (!value) {
    return "Never";
  }
  return new Date(value).toLocaleString();
}

function TrackerRow({
  tracker,
  onCheck,
  onUnfollow,
  onToggle,
  busy,
}: {
  tracker: SeriesTracker;
  onCheck: (id: number) => void;
  onUnfollow: (id: number) => void;
  onToggle: (id: number, enabled: boolean) => void;
  busy: boolean;
}) {
  const [migrateOpen, setMigrateOpen] = useState(false);
  // Downloaded trackers are derived from the download rows and would simply be
  // recreated at the old source on the next sync, so the endpoint refuses them.
  const canMigrate = tracker.track_kind === "followed";

  return (
    <div className="rounded-xl border border-border/40 bg-white/[0.02] p-4 transition-colors hover:border-primary/30">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium">{tracker.series_title}</p>
            <Badge variant={tracker.track_kind === "followed" ? "primary" : "default"}>
              {tracker.track_kind}
            </Badge>
            <Badge variant="default">{tracker.source}</Badge>
          </div>
          <p className="mt-1 text-sm text-muted">
            {tracker.known_chapter_count} known chapters · Last checked {formatWhen(tracker.last_checked_at)}
          </p>
          {tracker.last_error ? (
            <p className="mt-1 text-sm text-amber-600 dark:text-amber-400">{tracker.last_error}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={busy}
            onClick={() => onToggle(tracker.id, !tracker.enabled)}
          >
            {tracker.enabled ? "Disable" : "Enable"}
          </Button>
          <Button size="sm" variant="secondary" disabled={busy} onClick={() => onCheck(tracker.id)}>
            Check now
          </Button>
          {canMigrate ? (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => setMigrateOpen(true)}>
              <ArrowLeftRight className="size-3.5" aria-hidden />
              Move source
            </Button>
          ) : null}
          {tracker.track_kind === "followed" ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onUnfollow(tracker.id)}>
              Unfollow
            </Button>
          ) : null}
        </div>
      </div>

      {canMigrate && migrateOpen ? (
        <MigrateSeriesDialog tracker={tracker} onClose={() => setMigrateOpen(false)} />
      ) : null}
    </div>
  );
}

function NotificationRow({
  item,
  onRead,
  busy,
}: {
  item: UpdateNotification;
  onRead: (id: number) => void;
  busy: boolean;
}) {
  return (
    <div className={`rounded-xl border border-border/40 bg-white/[0.02] p-3 transition-colors hover:border-primary/30 ${item.is_read ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="font-medium">
            {item.series_title}
            <span className="text-muted"> · {item.chapter_title}</span>
          </p>
          <p className="text-sm text-muted">
            {item.source} · {formatWhen(item.created_at)}
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href={`/sources/${encodeURIComponent(item.source)}/series/${encodeURIComponent(item.series_id)}`}
            className="inline-flex h-8 items-center rounded-lg bg-surface-2 px-3 text-sm font-medium text-fg hover:bg-border"
          >
            Open
          </Link>
          {!item.is_read ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onRead(item.id)}>
              Mark read
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function UpdatesView() {
  const settings = useUpdateSettings();
  const followed = useTrackers("followed");
  const downloaded = useTrackers("downloaded");
  const notifications = useUpdateNotifications();
  const runs = useUpdateRuns();
  const manualCheck = useManualCheck();
  const syncDownloaded = useSyncDownloaded();
  const unfollow = useUnfollowTracker();
  const updateTracker = useUpdateTracker();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();

  const busy =
    manualCheck.isPending ||
    syncDownloaded.isPending ||
    unfollow.isPending ||
    updateTracker.isPending ||
    markRead.isPending ||
    markAllRead.isPending;

  const error =
    settings.error ??
    followed.error ??
    downloaded.error ??
    notifications.error ??
    runs.error;

  return (
    <div className="page-shell">
      <div className="page-container mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <HeroHeading className="leading-none md:text-6xl">
            Updates
          </HeroHeading>
          <p className="mt-2 text-sm text-muted">
            Track followed and downloaded series for new chapters.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <GhostPillButton
            disabled={busy}
            onClick={() => syncDownloaded.mutate()}
            icon={<RefreshCw className="size-4" aria-hidden />}
          >
            Sync Downloaded
          </GhostPillButton>
          <PrimaryPillButton
            disabled={busy}
            onClick={() => manualCheck.mutate({})}
            icon={<Search className="size-4" aria-hidden />}
          >
            Check All Now
          </PrimaryPillButton>
        </div>
      </div>

      {error instanceof ApiError ? (
        <div className="rounded-lg border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
          {error.message ?? "Failed to load updates"}
        </div>
      ) : null}

      {/* Settings used to be duplicated here AND in Settings; they now live in
          exactly one place. This is the pointer to it, plus the two facts the
          owner needs on this page to know whether checking is even happening. */}
      <Link
        href="/settings"
        className="group block focus-visible:outline-none"
        aria-label="Open update and notification settings"
      >
        <Card className="transition-colors group-hover:border-primary/40 group-focus-visible:border-primary/60">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
            <div className="flex min-w-0 items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/15 text-primary">
                <Bell className="size-5" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="font-medium text-fg">Update &amp; notification settings</p>
                <p className="mt-0.5 text-sm text-muted">
                  {settings.data
                    ? `${settings.data.enabled ? "Checking" : "Not checking"} every ${settings.data.check_interval_minutes} min · notifications ${settings.data.notify_enabled ? "on" : "off"} · last check ${formatWhen(settings.data.last_run_at)}`
                    : "Configure checks, notifications, and per-series alerts in Settings."}
                </p>
              </div>
            </div>
            <ChevronRight
              className="size-5 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
              aria-hidden
            />
          </CardContent>
        </Card>
      </Link>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Followed series</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {followed.isLoading ? (
              <div className="space-y-3" aria-busy="true">
                {Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className="h-24 animate-pulse rounded-lg bg-surface-2" />
                ))}
              </div>
            ) : (followed.data ?? []).length === 0 ? (
              <p className="text-sm text-muted">
                Follow series from the Sources browser to track new chapters.
              </p>
            ) : (
              (followed.data ?? []).map((tracker) => (
                <TrackerRow
                  key={tracker.id}
                  tracker={tracker}
                  busy={busy}
                  onCheck={(id) => manualCheck.mutate({ tracker_ids: [id] })}
                  onUnfollow={(id) => unfollow.mutate(id)}
                  onToggle={(id, enabled) => updateTracker.mutate({ id, body: { enabled } })}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Downloaded series</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {downloaded.isLoading ? (
              <div className="space-y-3" aria-busy="true">
                {Array.from({ length: 2 }).map((_, index) => (
                  <div key={index} className="h-24 animate-pulse rounded-lg bg-surface-2" />
                ))}
              </div>
            ) : (downloaded.data ?? []).length === 0 ? (
              <p className="text-sm text-muted">
                Completed downloads are tracked automatically after sync.
              </p>
            ) : (
              (downloaded.data ?? []).map((tracker) => (
                <TrackerRow
                  key={tracker.id}
                  tracker={tracker}
                  busy={busy}
                  onCheck={(id) => manualCheck.mutate({ tracker_ids: [id] })}
                  onUnfollow={() => undefined}
                  onToggle={(id, enabled) => updateTracker.mutate({ id, body: { enabled } })}
                />
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Notifications</CardTitle>
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || (notifications.data ?? []).every((n) => n.is_read)}
            onClick={() => markAllRead.mutate()}
          >
            Mark all read
          </Button>
        </CardHeader>
        <CardContent className="space-y-3">
          {notifications.isLoading ? (
            <div className="space-y-3" aria-busy="true">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="h-16 animate-pulse rounded-lg bg-surface-2" />
              ))}
            </div>
          ) : (notifications.data ?? []).length === 0 ? (
            <p className="text-sm text-muted">No notifications yet.</p>
          ) : (
            (notifications.data ?? []).map((item) => (
              <NotificationRow
                key={item.id}
                item={item}
                busy={busy}
                onRead={(id) => markRead.mutate(id)}
              />
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent checks</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {runs.isLoading ? (
            <div className="space-y-2" aria-busy="true">
              {Array.from({ length: 3 }).map((_, index) => (
                <div key={index} className="h-5 animate-pulse rounded bg-surface-2" />
              ))}
            </div>
          ) : (runs.data ?? []).length === 0 ? (
            <p className="text-sm text-muted">No check runs yet.</p>
          ) : (
            (runs.data ?? []).map((run) => (
              <div key={run.id} className="flex flex-wrap justify-between gap-2 text-sm">
                <span>
                  {run.trigger} · {run.status} · {run.series_checked} series ·{" "}
                  {run.new_chapters_found} new
                </span>
                <span className="text-muted">{formatWhen(run.started_at)}</span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
      </div>
    </div>
  );
}
