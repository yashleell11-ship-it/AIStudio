"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass } from "lucide-react";
import { useFollowedIndex } from "../hooks";
import { shouldShowFirstRunHint } from "../first-run";

/**
 * Quiet, app-wide nudge for a brand-new account: "you follow nothing yet, go
 * browse a source." Mounted once in the app shell (not per-screen) so it
 * reaches a fresh account wherever it lands first.
 *
 * Not a modal, not dismissible, not a wizard — it is driven entirely by the
 * followed-series count (`shouldShowFirstRunHint`), so it disappears the
 * instant that count leaves zero and can never nag: there is no "dismissed"
 * flag to reappear around.
 */
export function FirstRunHint() {
  const pathname = usePathname();
  const followedIndex = useFollowedIndex();
  const followedCount = followedIndex.isSuccess ? followedIndex.index.size : null;

  if (!shouldShowFirstRunHint({ followedCount, pathname })) {
    return null;
  }

  return (
    <div
      role="note"
      className="shrink-0 border-b border-primary/20 bg-primary/[0.06] px-4 py-2.5 md:px-8"
    >
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-3 gap-y-1.5">
        <Compass className="size-4 shrink-0 text-primary" aria-hidden />
        <p className="min-w-0 flex-1 text-sm leading-snug text-fg">
          <span className="font-medium">Nothing followed yet.</span>{" "}
          <span className="text-muted">
            Browse a source and follow a series to start building your library.
          </span>
        </p>
        <Link
          href="/sources"
          className="inline-flex h-10 shrink-0 items-center rounded-full border border-primary/30 bg-primary/10 px-4 text-xs font-medium text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          Browse Sources
        </Link>
      </div>
    </div>
  );
}
