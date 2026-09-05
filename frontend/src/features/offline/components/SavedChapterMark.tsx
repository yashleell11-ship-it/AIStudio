"use client";

import {
  Check,
  CircleDashed,
  CloudDownload,
  Loader2,
  PauseCircle,
  TriangleAlert,
} from "lucide-react";
import { cn } from "@/lib/cn";
import type { ChapterDownloadState } from "../series-downloads";

/**
 * What a chapter row says about the copy on this device.
 *
 * Before this, a series page said nothing at all: the only way to find out
 * whether a chapter was saved was to open it and look at the reader's control.
 * Every state here comes from the service worker's index, so it agrees with
 * `/downloads` by construction.
 *
 * "none" renders nothing rather than an empty slot — a list of 300 chapters
 * should not carry 300 grey placeholders for the ones you have not saved.
 */

const MARKS: Record<
  Exclude<ChapterDownloadState, "none">,
  { icon: typeof Check; label: string; className: string; spin?: boolean }
> = {
  queued: {
    icon: CircleDashed,
    label: "Queued to download",
    className: "text-muted",
  },
  saving: {
    icon: Loader2,
    label: "Downloading",
    className: "text-primary",
    spin: true,
  },
  saved: {
    icon: Check,
    label: "Downloaded — opens with no connection",
    className: "text-success",
  },
  incomplete: {
    icon: TriangleAlert,
    label: "Incomplete — some pages are missing",
    className: "text-warning",
  },
  paused: {
    icon: PauseCircle,
    label: "Paused — this browser is out of room",
    className: "text-warning",
  },
  stale: {
    icon: CloudDownload,
    label: "The source changed these pages — download it again",
    className: "text-warning",
  },
};

export function SavedChapterMark({
  state,
  className,
}: {
  state: ChapterDownloadState;
  className?: string;
}) {
  if (state === "none") return null;
  const mark = MARKS[state];
  const Icon = mark.icon;
  return (
    <span
      title={mark.label}
      className={cn("inline-flex shrink-0 items-center", mark.className, className)}
    >
      <Icon className={cn("size-4", mark.spin && "animate-spin")} aria-hidden />
      <span className="sr-only">{mark.label}</span>
    </span>
  );
}

/** The tick box a row grows while the list is in selection mode. */
export function ChapterCheckbox({
  checked,
  disabled,
}: {
  checked: boolean;
  disabled: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
        disabled
          ? "border-border/40 bg-white/[0.02] text-muted/40"
          : checked
            ? "border-primary bg-primary text-primary-fg"
            : "border-border bg-white/[0.03] text-transparent",
      )}
    >
      <Check className="size-3.5" />
    </span>
  );
}
