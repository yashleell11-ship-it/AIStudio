"use client";

import { Bookmark, BookmarkCheck, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/cn";

export type BookmarkNoticeTone = "saved" | "moved" | "failed";

const ICONS = {
  saved: BookmarkCheck,
  moved: Bookmark,
  failed: TriangleAlert,
} as const;

interface BookmarkNoticeProps {
  tone: BookmarkNoticeTone;
  children: React.ReactNode;
  /**
   * Palette override for the novel reader, whose page is painted in the
   * reader's chosen colours rather than the app's. The manga reader passes
   * nothing and gets the app surface.
   */
  style?: React.CSSProperties;
  className?: string;
}

/**
 * A one-line pill at the foot of a reader.
 *
 * Two things need saying inside a chapter and neither deserves a dialog: that
 * a position was captured, and — design §3 — that a restored position no
 * longer exists and the nearest one was used instead. "Say so quietly" is the
 * requirement, so this floats over the page, takes no clicks
 * (`pointer-events-none`) and is announced politely rather than asserted; the
 * caller decides how long it stays.
 *
 * Deliberately not a toast system. One component with three tones covers every
 * message this feature has, in both readers, and a general notification stack
 * would be more machinery than the app has any other use for.
 */
export function BookmarkNotice({
  tone,
  children,
  style,
  className,
}: BookmarkNoticeProps) {
  const Icon = ICONS[tone];
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center px-4",
        className,
      )}
    >
      <div
        className={cn(
          "flex max-w-[min(28rem,100%)] items-center gap-2 rounded-full border px-4 py-2 text-sm shadow-lg backdrop-blur",
          !style && "border-border bg-surface-2/95 text-fg",
          tone === "failed" && !style && "text-danger",
        )}
        style={style}
      >
        <Icon className="size-4 shrink-0" aria-hidden />
        <span className="min-w-0 truncate">{children}</span>
      </div>
    </div>
  );
}
