"use client";

import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ApiError } from "@/types/api";
import { useUpdateSettingsMutation } from "../hooks";
import type { UpdateSettings } from "../types";

interface UpdateSettingsPanelProps {
  settings: UpdateSettings | undefined;
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  onRetry?: () => void;
}

function ToggleRow({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-xl border border-border/40 bg-white/[0.02] px-4 py-3 transition-colors hover:border-violet-500/20">
      <div className="min-w-0">
        <p className="text-sm font-medium text-fg">{label}</p>
        {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} aria-label={label} />
    </div>
  );
}

function UpdateSettingsForm({ settings }: { settings: UpdateSettings }) {
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
      <div>
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
          Update checks
        </h3>
        <div className="space-y-2">
          <ToggleRow
            label="Automatic checks enabled"
            description="Periodically scan followed and downloaded series for new chapters."
            checked={draft.enabled}
            onCheckedChange={(enabled) => setDraft({ ...draft, enabled })}
          />
          <ToggleRow
            label="Check on startup"
            description="Run an update check when ManhwaManiacs launches."
            checked={draft.check_on_startup}
            onCheckedChange={(check_on_startup) => setDraft({ ...draft, check_on_startup })}
          />
          <ToggleRow
            label="Auto-download (future)"
            description="Automatically queue new chapters when they are found."
            checked={draft.auto_download_enabled}
            onCheckedChange={(auto_download_enabled) =>
              setDraft({ ...draft, auto_download_enabled })
            }
          />
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
          Notifications
        </h3>
        <ToggleRow
          label="Notifications enabled"
          description="Show alerts when new chapters are discovered."
          checked={draft.notify_enabled}
          onCheckedChange={(notify_enabled) => setDraft({ ...draft, notify_enabled })}
        />
      </div>

      <div className="rounded-xl border border-border/40 bg-white/[0.02] p-4">
        <label className="flex flex-col gap-3 text-sm">
          <div className="flex items-center justify-between gap-3">
            <span className="font-medium text-fg">Check interval</span>
            <span className="font-mono text-sm tabular-nums text-violet-400">
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
          <span className="text-xs text-muted">How often to check for new chapters (5–120 minutes).</span>
        </label>
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
    <div className="space-y-3" aria-busy="true" aria-label="Loading update settings">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-14 animate-pulse rounded-xl bg-surface-2" />
      ))}
    </div>
  );
}

export function UpdateSettingsPanel({
  settings,
  isLoading,
  isError,
  error,
  onRetry,
}: UpdateSettingsPanelProps) {
  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-violet-500/10 text-cyan-400">
          <RefreshCw className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-fg">General</h2>
          <p className="mt-0.5 text-sm text-muted">
            Automatic update checks and notification preferences.
          </p>
        </div>
      </div>

      {isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {error instanceof ApiError ? error.message : "Failed to load update settings."}
          </p>
          {onRetry ? (
            <Button variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : isLoading || !settings ? (
        <PanelSkeleton />
      ) : (
        <UpdateSettingsForm key={settings.updated_at ?? "default"} settings={settings} />
      )}
    </section>
  );
}
