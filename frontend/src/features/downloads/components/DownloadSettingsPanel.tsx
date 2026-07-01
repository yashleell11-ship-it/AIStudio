"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useDownloadSettings, useUpdateDownloadSettings } from "../hooks";
import type { DownloadSettings } from "../types";

const CONCURRENT_CHAPTER_OPTIONS = Array.from({ length: 10 }, (_, i) => i + 1);

const selectClassName = cn(
  "flex h-10 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
  "disabled:cursor-not-allowed disabled:opacity-50",
);

function parseNumberField(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function DownloadSettingsForm({
  initial,
  activeDownloadCount,
}: {
  initial: DownloadSettings;
  activeDownloadCount: number;
}) {
  const mutation = useUpdateDownloadSettings();
  // Seeded once from the first successful fetch. Deliberately not
  // re-synced from later background refetches (active_download_count
  // alone changes every few seconds while something is downloading) --
  // that would silently discard whatever the user is mid-editing.
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
      setFeedback("Saved. Takes effect immediately -- no restart needed.");
    } catch (error) {
      setFeedback(error instanceof ApiError ? error.message : "Failed to save settings.");
    }
  };

  return (
    <CardContent className="grid gap-4 md:grid-cols-2">
      <label className="flex flex-col gap-1 text-sm">
        Concurrent chapter downloads
        <select
          className={selectClassName}
          value={draft.download_concurrent_chapters}
          onChange={(e) =>
            setDraft({ ...draft, download_concurrent_chapters: Number(e.target.value) })
          }
        >
          {CONCURRENT_CHAPTER_OPTIONS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <span className="text-xs text-muted">
          How many chapters may download at once, across all series.
        </span>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Retry count
        <Input
          type="number"
          min={0}
          max={10}
          value={draft.download_retry_count}
          onChange={(e) =>
            setDraft({ ...draft, download_retry_count: parseNumberField(e.target.value, draft.download_retry_count) })
          }
        />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Retry delay (seconds)
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
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Download timeout (seconds)
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
      </label>

      <label className="flex flex-col gap-1 text-sm">
        Maximum simultaneous page downloads per chapter
        <Input
          type="number"
          min={1}
          max={10}
          value={draft.download_page_concurrency}
          onChange={(e) =>
            setDraft({
              ...draft,
              download_page_concurrency: parseNumberField(
                e.target.value,
                draft.download_page_concurrency,
              ),
            })
          }
        />
        <span className="text-xs text-muted">
          Advanced. Independent of the chapter limit above -- pages within a
          chapter may still fetch in parallel for performance.
        </span>
      </label>

      <div className="flex flex-col gap-1 text-sm">
        Active downloads right now
        <p className="text-lg font-semibold text-fg">{activeDownloadCount}</p>
      </div>

      <div className="flex items-end gap-3 md:col-span-2">
        <Button type="button" disabled={mutation.isPending} onClick={save}>
          Save settings
        </Button>
        {feedback && <p className="text-sm text-muted">{feedback}</p>}
      </div>
    </CardContent>
  );
}

export function DownloadSettingsPanel() {
  const settingsQuery = useDownloadSettings();

  if (settingsQuery.isError) {
    const message =
      settingsQuery.error instanceof ApiError
        ? settingsQuery.error.message
        : "Failed to load download settings.";
    return (
      <Card>
        <CardHeader>
          <CardTitle>Downloads</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-sm text-danger">{message}</p>
          <Button variant="secondary" onClick={() => settingsQuery.refetch()}>
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (settingsQuery.isLoading || !settingsQuery.data) {
    return (
      <Card aria-busy="true" aria-label="Loading download settings">
        <CardHeader>
          <CardTitle>Downloads</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-10 animate-pulse rounded bg-surface-2" />
          ))}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Downloads</CardTitle>
      </CardHeader>
      <DownloadSettingsForm
        initial={settingsQuery.data}
        activeDownloadCount={settingsQuery.data.active_download_count}
      />
    </Card>
  );
}
