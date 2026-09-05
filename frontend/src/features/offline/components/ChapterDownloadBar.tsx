"use client";

import Link from "next/link";
import { CloudDownload, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/cn";
import type { ChapterPicker } from "../use-chapter-picker";

/**
 * The multi-select strip on a series page: pick chapters, then download them.
 *
 * It stays mounted while a run is going, because the run is the thing that
 * needs watching — how far along it is, and what it ended up doing. A download
 * that reports nothing is how a reader ends up on a train with four of the ten
 * chapters they thought they had.
 */
export function ChapterDownloadBar({
  picker,
  className,
}: {
  picker: ChapterPicker;
  className?: string;
}) {
  const downloads = picker.downloads;
  const { progress, summary } = downloads;

  if (downloads.unavailable) return null;

  const percent =
    progress && progress.total > 0
      ? Math.round((progress.completed / progress.total) * 100)
      : 0;

  return (
    <div
      className={cn(
        "glass-panel sticky bottom-4 z-20 rounded-2xl border border-border/60 p-3",
        className,
      )}
    >
      {downloads.running && progress ? (
        <div className="flex flex-wrap items-center gap-3">
          <Loader2 className="size-4 shrink-0 animate-spin text-primary" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-fg">
              Downloading {progress.completed + (progress.current ? 1 : 0)} of{" "}
              {progress.total}
            </p>
            <Progress
              value={percent}
              className="mt-2 h-1"
              aria-label="Chapters downloaded"
            />
          </div>
          <Button variant="ghost" size="sm" onClick={downloads.cancel}>
            Stop
          </Button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-1 text-sm text-fg">
            {picker.selectedCount === 0
              ? "Select chapters to download"
              : `${picker.selectedCount} selected`}
            {/* Ticking a chapter that is already here is allowed — a
                shift-click range should not have holes in it — so when the two
                numbers differ, say which is which rather than letting the
                button silently download fewer than the count above it. */}
            {picker.plan.length < picker.selectedCount ? (
              <span className="ml-1.5 text-muted">
                · {picker.selectedCount - picker.plan.length} already downloaded
              </span>
            ) : null}
          </span>
          {picker.helpers.map((helper) => (
            <button
              key={helper.id}
              type="button"
              onClick={() => picker.applyHelper(helper.keys)}
              className="rounded-full border border-border/60 bg-white/[0.03] px-3 py-1 text-xs text-muted transition-colors hover:border-primary/40 hover:text-fg [@media(pointer:coarse)]:min-h-11"
            >
              {helper.label}
              <span className="ml-1.5 font-mono tabular-nums text-muted/70">
                {helper.keys.length}
              </span>
            </button>
          ))}
          <div className="ml-auto flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={picker.end}>
              <X className="size-4" aria-hidden />
              Done
            </Button>
            <Button
              size="sm"
              disabled={picker.plan.length === 0 || !downloads.scope}
              onClick={picker.start}
            >
              <CloudDownload className="size-4" aria-hidden />
              {picker.plan.length > 0 ? `Download ${picker.plan.length}` : "Download"}
            </Button>
          </div>
        </div>
      )}

      {summary ? (
        <p
          className={cn(
            "mt-2 flex flex-wrap items-center gap-2 text-xs",
            summary.tone === "warn" ? "text-warning" : "text-muted",
          )}
          role="status"
        >
          {summary.label}
          <Link href="/downloads" className="underline underline-offset-2 hover:text-fg">
            Manage downloads
          </Link>
          <button
            type="button"
            onClick={downloads.dismissSummary}
            className="text-muted/70 underline underline-offset-2 hover:text-fg"
          >
            Dismiss
          </button>
        </p>
      ) : null}

      {!downloads.scope ? (
        <p className="mt-2 text-xs text-muted">
          Downloads belong to a reading profile. Choose one to save chapters here.
        </p>
      ) : null}
    </div>
  );
}

/**
 * The way into selection mode, and the standing count of what is already here —
 * the only place a series page has ever stated it. The count is dropped when it
 * is zero: "0 of 84 downloaded" is noise beside a button that says Download.
 */
export function ChapterDownloadTrigger({
  picker,
  label = "Download",
}: {
  picker: ChapterPicker;
  label?: string;
}) {
  if (picker.downloads.unavailable) return null;
  return (
    <div className="flex items-center gap-3">
      {picker.savedCount > 0 ? (
        <span className="text-xs text-muted">
          {picker.savedCount} of {picker.total} downloaded
        </span>
      ) : null}
      <Button variant="secondary" size="sm" onClick={picker.begin}>
        <CloudDownload className="size-4" aria-hidden />
        {label}
      </Button>
    </div>
  );
}
