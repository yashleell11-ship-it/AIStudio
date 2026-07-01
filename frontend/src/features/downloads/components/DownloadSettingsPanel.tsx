"use client";

import { useState } from "react";
import { Download, Gauge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useDownloadSettings, useUpdateDownloadSettings } from "../hooks";
import type { DownloadSettings } from "../types";

function parseNumberField(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function SettingsField({
  label,
  hint,
  children,
  className,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex flex-col gap-2 text-sm", className)}>
      <span className="font-medium text-fg">{label}</span>
      {children}
      {hint ? <span className="text-xs leading-relaxed text-muted">{hint}</span> : null}
    </label>
  );
}

function SliderField({
  label,
  hint,
  value,
  min,
  max,
  step,
  unit,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  return (
    <SettingsField label={label} hint={hint}>
      <div className="flex items-center gap-3">
        <Slider
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={onChange}
          aria-label={label}
          className="flex-1"
        />
        <span className="w-12 shrink-0 text-right font-mono text-sm tabular-nums text-violet-400">
          {value}
          {unit}
        </span>
      </div>
    </SettingsField>
  );
}

function DownloadSettingsForm({
  initial,
  activeDownloadCount,
}: {
  initial: DownloadSettings;
  activeDownloadCount: number;
}) {
  const mutation = useUpdateDownloadSettings();
  const [draft, setDraft] = useState(initial);
  const [feedback, setFeedback] = useState<string | null>(null);

  const save = async () => {
    setFeedback(null);
    try {
      await mutation.mutateAsync({
        download_concurrent_chapters: draft.download_concurrent_chapters,
        download_page_concurrency: draft.download_page_concurrency,
        download_retry_count: draft.download_retry_count,
        download_retry_delay_seconds: draft.download_retry_delay_seconds,
        download_timeout_seconds: draft.download_timeout_seconds,
      });
      setFeedback("Saved. Takes effect immediately — no restart needed.");
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to save settings.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid gap-5 md:grid-cols-2">
        <SliderField
          label="Concurrent chapter downloads"
          hint="How many chapters may download at once, across all series."
          value={draft.download_concurrent_chapters}
          min={1}
          max={10}
          onChange={(value) => setDraft({ ...draft, download_concurrent_chapters: value })}
        />

        <SliderField
          label="Page downloads per chapter"
          hint="Advanced. Pages within a chapter may still fetch in parallel."
          value={draft.download_page_concurrency}
          min={1}
          max={10}
          onChange={(value) => setDraft({ ...draft, download_page_concurrency: value })}
        />

        <SettingsField label="Retry count">
          <Input
            type="number"
            min={0}
            max={10}
            value={draft.download_retry_count}
            onChange={(e) =>
              setDraft({
                ...draft,
                download_retry_count: parseNumberField(e.target.value, draft.download_retry_count),
              })
            }
          />
        </SettingsField>

        <SettingsField label="Retry delay (seconds)">
          <Input
            type="number"
            min={0}
            max={30}
            step={0.1}
            value={draft.download_retry_delay_seconds}
            onChange={(e) =>
              setDraft({
                ...draft,
                download_retry_delay_seconds: parseNumberField(
                  e.target.value,
                  draft.download_retry_delay_seconds,
                ),
              })
            }
          />
        </SettingsField>

        <SettingsField label="Download timeout (seconds)">
          <Input
            type="number"
            min={1}
            max={300}
            value={draft.download_timeout_seconds}
            onChange={(e) =>
              setDraft({
                ...draft,
                download_timeout_seconds: parseNumberField(
                  e.target.value,
                  draft.download_timeout_seconds,
                ),
              })
            }
          />
        </SettingsField>

        <div className="glass-card flex flex-col justify-center rounded-xl p-4">
          <div className="flex items-center gap-2 text-sm text-muted">
            <Gauge className="size-4 text-cyan-400" aria-hidden />
            Active downloads right now
          </div>
          <p className="mt-1 font-display text-3xl tabular-nums text-fg">{activeDownloadCount}</p>
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
    <div className="space-y-4" aria-busy="true" aria-label="Loading download settings">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-12 animate-pulse rounded-xl bg-surface-2" />
      ))}
    </div>
  );
}

export function DownloadSettingsPanel() {
  const settingsQuery = useDownloadSettings();

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/20 to-cyan-500/10 text-violet-400">
          <Download className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-fg">Downloads</h2>
          <p className="mt-0.5 text-sm text-muted">
            Control queue concurrency, retries, and timeouts for chapter downloads.
          </p>
        </div>
      </div>

      {settingsQuery.isError ? (
        <div className="space-y-3">
          <p className="text-sm text-danger">
            {settingsQuery.error instanceof ApiError
              ? settingsQuery.error.message
              : "Failed to load download settings."}
          </p>
          <Button variant="secondary" onClick={() => settingsQuery.refetch()}>
            Try again
          </Button>
        </div>
      ) : settingsQuery.isLoading || !settingsQuery.data ? (
        <PanelSkeleton />
      ) : (
        <DownloadSettingsForm
          initial={settingsQuery.data}
          activeDownloadCount={settingsQuery.data.active_download_count}
        />
      )}
    </section>
  );
}
