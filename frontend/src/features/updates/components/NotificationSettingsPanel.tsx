"use client";

import { useMemo, useState } from "react";
import { Bell, BellOff, Clock, Search, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useTrackers, useUpdateSettings, useUpdateSettingsMutation, useUpdateTracker } from "../hooks";
import {
  buildNotificationRows,
  describeCheckSchedule,
  summarizeNotificationCoverage,
  type NotificationTrackerRow,
} from "../notifications";
import type { UpdateSettings } from "../types";

function formatWhen(value: string | null | undefined): string {
  if (!value) return "Never";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return "Unknown";
  return new Date(parsed).toLocaleString();
}

function ToggleRow({
  label,
  description,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-border/40 bg-white/[0.02] px-4 py-3 transition-colors hover:border-primary/30">
      <div className="min-w-0">
        <p className="text-sm font-medium text-fg">{label}</p>
        {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
      </div>
      <Switch
        checked={checked}
        disabled={disabled}
        onCheckedChange={onCheckedChange}
        aria-label={label}
      />
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
      {children}
    </h3>
  );
}

/** Read-only summary of when the checker last ran and when it runs next. */
function ScheduleStrip({ settings }: { settings: UpdateSettings }) {
  // Sampled once per mount rather than on every render: this strip is
  // informational, and a clock that ticks under the user's cursor while they
  // are toggling switches is noise.
  const [nowMs] = useState(() => Date.now());
  const schedule = describeCheckSchedule(settings, nowMs);
  if (!schedule) return null;

  return (
    <div className="grid gap-2 rounded-xl border border-border/40 bg-white/[0.02] p-4 sm:grid-cols-3">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">Last check</p>
        <p className="mt-0.5 text-sm text-fg">{formatWhen(schedule.lastRunAt)}</p>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">Next check (est.)</p>
        <p className={cn("mt-0.5 text-sm", schedule.overdue ? "text-warning" : "text-fg")}>
          {schedule.neverRun ? "Not scheduled yet" : formatWhen(schedule.estimatedNextRunAt)}
        </p>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">Interval</p>
        <p className="mt-0.5 text-sm text-fg">{schedule.intervalMinutes} min</p>
      </div>
      {schedule.overdue ? (
        <p className="sm:col-span-3 text-xs text-warning">
          The next check was expected {schedule.overdueByMinutes} minutes ago. See{" "}
          <span className="font-medium">System Status</span> for whether the scheduler is running.
        </p>
      ) : null}
    </div>
  );
}

function GlobalSettingsForm({ settings }: { settings: UpdateSettings }) {
  const mutation = useUpdateSettingsMutation();
  const [draft, setDraft] = useState(settings);
  const [feedback, setFeedback] = useState<string | null>(null);

  const save = async () => {
    setFeedback(null);
    try {
      await mutation.mutateAsync({
        enabled: draft.enabled,
        check_interval_minutes: draft.check_interval_minutes,
        notify_enabled: draft.notify_enabled,
        auto_download_enabled: draft.auto_download_enabled,
        check_on_startup: draft.check_on_startup,
      });
      setFeedback("Saved.");
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to save settings.");
    }
  };

  return (
    <div className="space-y-6">
      <ScheduleStrip settings={settings} />

      <div>
        <SectionHeading>Update checks</SectionHeading>
        <div className="space-y-2">
          <ToggleRow
            label="Check for new chapters automatically"
            description="Nothing is checked and nothing notifies while this is off."
            checked={draft.enabled}
            onCheckedChange={(enabled) => setDraft({ ...draft, enabled })}
          />
          <ToggleRow
            label="Check on startup"
            description="Run one check as soon as the server starts."
            checked={draft.check_on_startup}
            onCheckedChange={(check_on_startup) => setDraft({ ...draft, check_on_startup })}
          />
        </div>
      </div>

      <div className="rounded-xl border border-border/40 bg-white/[0.02] p-4">
        <label className="flex flex-col gap-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2 font-medium text-fg">
              <Clock className="size-4 text-primary" aria-hidden />
              Check interval
            </span>
            <span className="font-mono text-sm tabular-nums text-primary">
              {draft.check_interval_minutes} min
            </span>
          </div>
          <Slider
            value={draft.check_interval_minutes}
            min={5}
            max={120}
            step={5}
            onChange={(check_interval_minutes) => setDraft({ ...draft, check_interval_minutes })}
            aria-label="Check interval in minutes"
          />
          <span className="text-xs text-muted">
            How often followed and downloaded series are checked (5–120 minutes). The server
            enforces a five-minute floor.
          </span>
        </label>
      </div>

      <div>
        <SectionHeading>New-chapter notifications</SectionHeading>
        <div className="space-y-2">
          <ToggleRow
            label="Notify me about new chapters"
            description="The master switch. Individual series can still be silenced below."
            checked={draft.notify_enabled}
            onCheckedChange={(notify_enabled) => setDraft({ ...draft, notify_enabled })}
          />
          <ToggleRow
            label="Auto-download new chapters"
            description="Queue new chapters as soon as a check finds them, for series that opt in."
            checked={draft.auto_download_enabled}
            onCheckedChange={(auto_download_enabled) =>
              setDraft({ ...draft, auto_download_enabled })
            }
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-border/40 pt-5">
        <Button type="button" disabled={mutation.isPending} onClick={save}>
          {mutation.isPending ? "Saving…" : "Save settings"}
        </Button>
        {feedback ? <p className="text-sm text-muted">{feedback}</p> : null}
      </div>
    </div>
  );
}

function PerSeriesRow({
  row,
  disabled,
  onToggle,
}: {
  row: NotificationTrackerRow;
  disabled: boolean;
  onToggle: (notify: boolean) => void;
}) {
  const { tracker } = row;
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border/40 bg-white/[0.02] px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate text-sm font-medium text-fg">{tracker.series_title}</p>
          <Badge variant={tracker.track_kind === "followed" ? "primary" : "default"}>
            {tracker.track_kind}
          </Badge>
          <Badge variant="default" className="font-mono">
            {tracker.source}
          </Badge>
          {row.duplicateTitle ? (
            <Badge variant="default" title="Followed on more than one source — each notifies separately.">
              also followed elsewhere
            </Badge>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-muted">
          {tracker.known_chapter_count} known chapters · last checked{" "}
          {formatWhen(tracker.last_checked_at)}
        </p>
        {tracker.last_error ? (
          <p className="mt-1 inline-flex items-start gap-1.5 break-words text-xs text-danger">
            <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden />
            {tracker.last_error}
          </p>
        ) : null}
        {!row.effectiveNotify && tracker.notify ? (
          <p className="mt-1 inline-flex items-center gap-1.5 text-xs text-warning">
            <BellOff className="size-3.5 shrink-0" aria-hidden />
            {row.silencedReason}
          </p>
        ) : null}
      </div>
      <Switch
        checked={tracker.notify}
        disabled={disabled}
        onCheckedChange={onToggle}
        aria-label={`Notify about new chapters of ${tracker.series_title} on ${tracker.source}`}
      />
    </li>
  );
}

function PerSeriesSection({ settings }: { settings: UpdateSettings | undefined }) {
  const trackers = useTrackers();
  const updateTracker = useUpdateTracker();
  const [query, setQuery] = useState("");

  const rows = useMemo(
    () => buildNotificationRows(trackers.data, settings),
    [trackers.data, settings],
  );
  const coverage = useMemo(() => summarizeNotificationCoverage(rows), [rows]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (row) =>
        row.tracker.series_title.toLowerCase().includes(needle) ||
        row.tracker.source.toLowerCase().includes(needle),
    );
  }, [rows, query]);

  return (
    <div className="space-y-3 border-t border-border/40 pt-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <SectionHeading>Per-series notifications</SectionHeading>
          <p className="text-sm text-muted">
            {coverage.total === 0
              ? "No series is being tracked yet."
              : `${coverage.notifying} of ${coverage.total} tracked series will notify.` +
                (coverage.failing > 0
                  ? ` ${coverage.failing} failed their last check.`
                  : "")}
          </p>
        </div>
        {rows.length > 8 ? (
          <label className="relative w-full sm:w-64">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
              aria-hidden
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by title or source"
              aria-label="Filter tracked series"
              className="pl-9"
            />
          </label>
        ) : null}
      </div>

      {trackers.isLoading ? (
        <div className="space-y-2" aria-busy="true" aria-label="Loading tracked series">
          {Array.from({ length: 3 }).map((_, index) => (
            <div key={index} className="h-16 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </div>
      ) : trackers.isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {trackers.error instanceof ApiError
              ? trackers.error.message
              : "Failed to load tracked series."}
          </p>
          <Button variant="secondary" onClick={() => trackers.refetch()}>
            Try again
          </Button>
        </div>
      ) : rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border/50 px-4 py-6 text-center text-sm text-muted">
          Follow a series from the Sources browser, or download one, and it will appear here with
          its own notification switch.
        </p>
      ) : visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border/50 px-4 py-6 text-center text-sm text-muted">
          No tracked series matches “{query}”.
        </p>
      ) : (
        <ul className="space-y-2">
          {visible.map((row) => (
            <PerSeriesRow
              key={row.tracker.id}
              row={row}
              disabled={updateTracker.isPending}
              onToggle={(notify) =>
                updateTracker.mutate({ id: row.tracker.id, body: { notify } })
              }
            />
          ))}
        </ul>
      )}

      {updateTracker.isError ? (
        <p className="text-sm text-danger">
          {updateTracker.error instanceof ApiError
            ? updateTracker.error.message
            : "Failed to update that series."}
        </p>
      ) : null}

      {/* Following one story on two sources is two trackers server-side, and
          each one notifies on its own. That is intended behaviour, not a bug to
          de-duplicate — so it is explained rather than silently collapsed. */}
      <p className="text-xs leading-relaxed text-muted">
        Following the same story on more than one source keeps a separate tracker per source, and
        each one notifies separately. Turn off the switch on whichever you do not want to hear
        from.
      </p>
    </div>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-label="Loading notification settings">
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-xl bg-surface-2" />
      ))}
    </div>
  );
}

/**
 * The single home for update-check and new-chapter notification preferences.
 *
 * Consolidated here on purpose: these controls used to render both on /updates
 * and in Settings, which meant two places to look and two places to be wrong
 * about. /updates now links here instead.
 */
export function NotificationSettingsPanel() {
  const settings = useUpdateSettings();

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <Bell className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-fg">Updates &amp; notifications</h2>
          <p className="mt-0.5 text-sm text-muted">
            When new chapters are looked for, and which series tell you about them.
          </p>
        </div>
      </div>

      {settings.isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {settings.error instanceof ApiError
              ? settings.error.message
              : "Failed to load update settings."}
          </p>
          <Button variant="secondary" onClick={() => settings.refetch()}>
            Try again
          </Button>
        </div>
      ) : settings.isLoading || !settings.data ? (
        <PanelSkeleton />
      ) : (
        <div className="space-y-6">
          {/* Remount the draft form whenever the server's copy changes, so a
              save elsewhere is never overwritten by a stale draft. */}
          <GlobalSettingsForm
            key={settings.data.updated_at ?? "default"}
            settings={settings.data}
          />
          <PerSeriesSection settings={settings.data} />
        </div>
      )}
    </section>
  );
}
