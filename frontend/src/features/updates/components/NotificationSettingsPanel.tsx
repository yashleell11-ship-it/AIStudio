"use client";

import { useState } from "react";
import { Bell, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useUpdateSettings, useUpdateSettingsMutation } from "../hooks";
import { describeCheckSchedule } from "../notifications";
import { toSettingsUpdatePayload } from "../notification-link";
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
        {description ? (
          <p className="mt-0.5 text-xs text-muted">{description}</p>
        ) : null}
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
  const [nowMs] = useState(() => Date.now());
  const schedule = describeCheckSchedule(settings, nowMs);
  if (!schedule) return null;

  return (
    <div className="grid gap-2 rounded-xl border border-border/40 bg-white/[0.02] p-4 sm:grid-cols-3">
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">
          Last check
        </p>
        <p className="mt-0.5 text-sm text-fg">{formatWhen(schedule.lastRunAt)}</p>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">
          Next check (est.)
        </p>
        <p
          className={cn(
            "mt-0.5 text-sm",
            schedule.overdue ? "text-warning" : "text-fg",
          )}
        >
          {schedule.neverRun
            ? "Not scheduled yet"
            : formatWhen(schedule.estimatedNextRunAt)}
        </p>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted">Interval</p>
        <p className="mt-0.5 text-sm text-fg">{schedule.intervalMinutes} min</p>
      </div>
      {schedule.overdue ? (
        <p className="sm:col-span-3 text-xs text-warning">
          The next check was expected {schedule.overdueByMinutes} minutes ago. See{" "}
          <span className="font-medium">System Status</span> for whether the
          scheduler is running.
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
      // No `auto_download` — 1a dropped the server download engine (spec §3.6).
      await mutation.mutateAsync(toSettingsUpdatePayload(draft));
      setFeedback("Saved.");
    } catch (error) {
      setFeedback(
        error instanceof ApiError ? error.message : "Failed to save settings.",
      );
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
            onCheckedChange={(check_on_startup) =>
              setDraft({ ...draft, check_on_startup })
            }
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
            onChange={(check_interval_minutes) =>
              setDraft({ ...draft, check_interval_minutes })
            }
            aria-label="Check interval in minutes"
          />
          <span className="text-xs text-muted">
            How often followed series are checked (5–120 minutes). The server
            enforces a five-minute floor.
          </span>
        </label>
      </div>

      <div>
        <SectionHeading>New-chapter notifications</SectionHeading>
        <div className="space-y-2">
          <ToggleRow
            label="Notify me about new chapters"
            description="The master switch. Turn a single series off from its own page."
            checked={draft.notify_enabled}
            onCheckedChange={(notify_enabled) =>
              setDraft({ ...draft, notify_enabled })
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

function PanelSkeleton() {
  return (
    <div
      className="space-y-3"
      aria-busy="true"
      aria-label="Loading notification settings"
    >
      {Array.from({ length: 5 }).map((_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-xl bg-surface-2" />
      ))}
    </div>
  );
}

/**
 * The single home for update-check and new-chapter notification preferences
 * (spec §3.6). Global switches only — a series is silenced from its own page,
 * which patches the followed-series `notify` flag.
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
          <h2 className="text-lg font-semibold text-fg">
            Updates &amp; notifications
          </h2>
          <p className="mt-0.5 text-sm text-muted">
            When new chapters are looked for, and whether they tell you.
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
        <GlobalSettingsForm
          key={settings.data.last_run_at ?? "default"}
          settings={settings.data}
        />
      )}
    </section>
  );
}
