"use client";

import { BookCheck, Loader2, Star, StarOff, Trash2, Undo2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/cn";
import type { BulkProgress } from "../bulk";
import type { BulkAction } from "../hooks";
import type { Tag } from "../types";

interface BulkActionBarProps {
  count: number;
  visibleCount: number;
  allSelected: boolean;
  running: boolean;
  progress: BulkProgress | null;
  /** Result of the last run; keeps the bar up after the selection is cleared. */
  message: string | null;
  /** A bulk remove is undoable while its ids are still remembered. */
  undoAvailable: boolean;
  tags: Tag[];
  onRun: (action: BulkAction) => void;
  onSelectAll: () => void;
  onClear: () => void;
  onCancel: () => void;
  onUndo: () => void;
  onDismissMessage: () => void;
}

export function BulkActionBar({
  count,
  visibleCount,
  allSelected,
  running,
  progress,
  message,
  undoAvailable,
  tags,
  onRun,
  onSelectAll,
  onClear,
  onCancel,
  onUndo,
  onDismissMessage,
}: BulkActionBarProps) {
  if (count === 0 && message === null) {
    return null;
  }

  const percent =
    progress && progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-4">
      <div
        className="glass-panel pointer-events-auto w-full max-w-4xl rounded-2xl border border-border/60 p-3 shadow-glass"
        role="region"
        aria-label="Bulk actions"
      >
        {running && progress ? (
          <div className="flex items-center gap-3">
            <Loader2 className="size-4 shrink-0 animate-spin text-primary" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-fg">
                {progress.completed} of {progress.total}
                {progress.failed > 0 ? ` · ${progress.failed} failed` : ""}
              </p>
              <Progress
                value={percent}
                className="mt-1.5"
                aria-label="Bulk action progress"
              />
            </div>
            <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
              Stop
            </Button>
          </div>
        ) : count === 0 && message ? (
          <div className="flex items-center gap-3">
            <p className="min-w-0 flex-1 truncate text-sm text-fg">{message}</p>
            {undoAvailable ? (
              <Button type="button" variant="secondary" size="sm" onClick={onUndo}>
                <Undo2 className="size-4" />
                Undo
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onDismissMessage}
              aria-label="Dismiss"
            >
              <X className="size-4" />
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm font-medium text-fg">
              {count} selected
            </span>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onSelectAll}
              disabled={allSelected}
            >
              Select all {visibleCount}
            </Button>

            <span className="mx-1 h-5 w-px bg-border/60" aria-hidden />

            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onRun({ kind: "favorite", value: true })}
            >
              <Star className="size-4" />
              Favourite
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onRun({ kind: "favorite", value: false })}
            >
              <StarOff className="size-4" />
              Unfavourite
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onRun({ kind: "reading_status", value: "completed" })}
            >
              <BookCheck className="size-4" />
              Mark read
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => onRun({ kind: "reading_status", value: "unread" })}
            >
              Mark unread
            </Button>

            <select
              value=""
              onChange={(event) => {
                const tagId = Number(event.target.value);
                if (Number.isInteger(tagId) && tagId > 0) {
                  onRun({ kind: "tag", tagId });
                }
              }}
              disabled={tags.length === 0}
              aria-label="Add tag to selected series"
              className={cn(
                "h-8 rounded-lg border border-border/50 bg-white/[0.04] px-3 text-sm text-fg",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
                "disabled:cursor-not-allowed disabled:opacity-50",
              )}
            >
              <option value="">{tags.length === 0 ? "No tags yet" : "Add tag…"}</option>
              {tags.map((tag) => (
                <option key={tag.id} value={tag.id}>
                  {tag.name}
                </option>
              ))}
            </select>

            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={() => onRun({ kind: "membership", inLibrary: false })}
            >
              <Trash2 className="size-4" />
              Remove
            </Button>

            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onClear}
              className="ml-auto"
            >
              Clear
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
