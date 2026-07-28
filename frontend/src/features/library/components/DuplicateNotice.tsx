"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ChevronDown, ChevronUp, Copy, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { coverUrl } from "../api";
import { type DuplicateGroup, duplicateSurplusCount } from "../duplicates";
import type { SeriesSummary } from "../types";

interface DuplicateNoticeProps {
  groups: DuplicateGroup[];
  /** How many series were examined, and how many exist — see {@link DuplicateNotice}. */
  scanned: number;
  total: number;
  /** Unfollow one copy. Never called automatically. */
  onUnfollow: (seriesId: number) => void;
  pendingId: number | null;
}

function subtitle(series: SeriesSummary): string {
  const parts = [`${series.chapter_count} chapters`];
  if (series.read_chapters > 0) {
    parts.push(`${series.read_chapters} read`);
  }
  if (series.author) {
    parts.push(series.author);
  }
  return parts.join(" · ");
}

/**
 * Advisory duplicate suggestions.
 *
 * Collapsed to a single line by default and dismissible for the session: the
 * owner asked that following the same series twice stay legal, so this must
 * read as a note, not as a problem the library is nagging about. Nothing here
 * merges or unfollows on its own — every removal is one explicit click on one
 * named copy, and it removes only that copy's membership, leaving the other to
 * keep notifying separately.
 */
export function DuplicateNotice({
  groups,
  scanned,
  total,
  onUnfollow,
  pendingId,
}: DuplicateNoticeProps) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  if (groups.length === 0 || dismissed) {
    return null;
  }

  const surplus = duplicateSurplusCount(groups);

  return (
    <div className="mb-6 rounded-xl border border-border/50 bg-white/[0.03]">
      <div className="flex items-center gap-2 px-4 py-2.5">
        <Copy className="size-4 shrink-0 text-muted" aria-hidden />
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm text-muted transition-colors hover:text-fg"
        >
          <span className="truncate">
            {groups.length} {groups.length === 1 ? "title looks" : "titles look"} followed
            more than once ({surplus} extra {surplus === 1 ? "copy" : "copies"})
          </span>
          {open ? (
            <ChevronUp className="size-4 shrink-0" aria-hidden />
          ) : (
            <ChevronDown className="size-4 shrink-0" aria-hidden />
          )}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss duplicate suggestions"
          className="rounded-md p-1 text-muted transition-colors hover:bg-white/5 hover:text-fg"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      {open ? (
        <div className="space-y-4 border-t border-border/50 px-4 py-4">
          <p className="text-xs text-muted">
            Matched on title alone, so some of these are genuinely different
            series. Keeping both is fine — each copy tracks its own new chapters.
            {scanned < total
              ? ` Checked the first ${scanned.toLocaleString()} of ${total.toLocaleString()} series.`
              : ""}
          </p>

          {groups.map((group) => (
            <div key={group.key} className="space-y-2">
              <p className="text-sm font-medium text-fg">{group.title}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {group.series.map((series, index) => (
                  <div
                    key={series.id}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border border-border/40 bg-white/[0.02] p-2",
                      index === 0 && "border-primary/30",
                    )}
                  >
                    <Link
                      href={`/library/${series.id}`}
                      className="relative size-10 shrink-0 overflow-hidden rounded bg-surface-2"
                    >
                      <Image
                        src={coverUrl(series.id)}
                        alt={series.title}
                        fill
                        className="object-cover"
                        sizes="40px"
                        unoptimized
                      />
                    </Link>
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/library/${series.id}`}
                        className="block truncate text-sm text-fg hover:text-primary"
                      >
                        {series.title}
                      </Link>
                      <p className="truncate text-xs text-muted">{subtitle(series)}</p>
                    </div>
                    {index === 0 ? (
                      <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-primary">
                        Most read
                      </span>
                    ) : (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={pendingId === series.id}
                        onClick={() => onUnfollow(series.id)}
                      >
                        {pendingId === series.id ? "Removing…" : "Unfollow"}
                      </Button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
