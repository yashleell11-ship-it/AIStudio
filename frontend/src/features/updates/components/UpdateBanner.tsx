"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import {
  computeNewChaptersBanner,
  type NewChaptersBannerState,
  useUpdateNotifications,
} from "../hooks";

/**
 * sessionStorage key holding the highest notification id the user has dismissed
 * the banner for. Session-scoped on purpose: a dismissal is forgotten when the
 * browser session ends, but *newer* chapters (a higher id) re-surface the
 * banner within the same session.
 */
const BANNER_DISMISS_KEY = "mm.updates.banner.dismissedMaxId";

function readDismissedMaxId(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(BANNER_DISMISS_KEY);
  if (raw === null) return null;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Drives the banner. Reuses the same unread-notifications cache as the
 * notification bell (no extra polling) and tracks a session-scoped dismissal
 * watermark so dismissing sticks until newer chapters arrive.
 */
function useNewChaptersBanner(): NewChaptersBannerState & { dismiss: () => void } {
  const { data } = useUpdateNotifications(true);
  const [dismissedMaxId, setDismissedMaxId] = useState<number | null>(readDismissedMaxId);

  const state = computeNewChaptersBanner(data, dismissedMaxId);

  const dismiss = useCallback(() => {
    if (state.latestId === null) return;
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(BANNER_DISMISS_KEY, String(state.latestId));
    }
    setDismissedMaxId(state.latestId);
  }, [state.latestId]);

  return { ...state, dismiss };
}

/**
 * Routes where a bottom banner would be intrusive or redundant, so it is
 * suppressed: the immersive chapter reader, and the Updates page itself.
 */
function isSuppressedPath(pathname: string): boolean {
  return (
    /^\/reader\/\d+\/\d+/.test(pathname) ||
    /^\/reader\/online\//.test(pathname) ||
    pathname === "/updates"
  );
}

/**
 * App-shell banner announcing unread new chapters from followed/downloaded
 * series. Self-contained: owns its query and session-scoped dismissal, renders
 * `null` when there is nothing to show. Fixed to the bottom so it never sits
 * inside the reader's scroll container.
 */
export function UpdateBanner() {
  const pathname = usePathname();
  const { show, count, seriesCount, dismiss } = useNewChaptersBanner();

  if (!show || isSuppressedPath(pathname)) return null;

  const chapterLabel = `${count} new chapter${count === 1 ? "" : "s"}`;
  const seriesLabel = seriesCount > 1 ? ` across ${seriesCount} series` : "";

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 flex justify-center p-4">
      <div
        role="status"
        aria-live="polite"
        className={cn(
          "pointer-events-auto flex w-full max-w-2xl items-center gap-3 rounded-xl",
          "border border-border/50 bg-surface-2 px-4 py-3 shadow-glow",
        )}
      >
        <BookOpenCheck className="size-5 shrink-0 text-primary" aria-hidden />
        <p className="min-w-0 flex-1 text-sm text-fg">
          <span className="font-medium">{chapterLabel}</span>
          {seriesLabel} available to read.
        </p>
        <Link
          href="/updates"
          onClick={dismiss}
          className="inline-flex h-9 shrink-0 items-center rounded-lg border border-border/50 px-3 text-sm font-medium text-fg transition-colors hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          View updates
        </Link>
        <Button
          variant="ghost"
          size="icon"
          onClick={dismiss}
          aria-label="Dismiss new chapters notification"
        >
          <X className="size-4" aria-hidden />
        </Button>
      </div>
    </div>
  );
}
