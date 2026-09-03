"use client";

import { useCallback, useEffect, useRef } from "react";
import { WifiOff } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { offlineDescription, shouldAutoRetry } from "@/lib/offline-recovery";

export interface OfflineStateProps {
  /**
   * The screen-specific lead sentence, e.g. "Your library needs a connection to
   * load." The shared "downloaded chapters still open" line is appended.
   */
  reason: string;
  /** Re-runs the query that failed. */
  onRetry?: () => void;
  className?: string;
}

/**
 * The one "the server could not be reached" card, for the ten screens that
 * render one.
 *
 * The offline state used to be a dead end — it explained the problem, pointed
 * at Downloads, and then sat there until the reader thought to reload. This one
 * offers a real Try again, and re-runs the query BY ITSELF the moment the
 * browser reports the connection back, so a state caused by a dropped wifi
 * clears without anyone touching it.
 */
export function OfflineState({ reason, onRetry, className }: OfflineStateProps) {
  const lastRetryAt = useRef<number | null>(null);
  const retryRef = useRef(onRetry);

  useEffect(() => {
    retryRef.current = onRetry;
  }, [onRetry]);

  const retry = useCallback(() => {
    lastRetryAt.current = Date.now();
    retryRef.current?.();
  }, []);

  useEffect(() => {
    const onOnline = () => {
      if (
        !shouldAutoRetry({
          online: navigator.onLine,
          lastRetryAt: lastRetryAt.current,
          now: Date.now(),
        })
      ) {
        return;
      }
      retry();
    };
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [retry]);

  return (
    <EmptyState
      tone="offline"
      icon={WifiOff}
      title="You're offline"
      description={offlineDescription(reason)}
      // Downloads stays reachable either way; it is only the fallback headline
      // action on the rare screen with nothing to re-run.
      action={
        onRetry
          ? { label: "Try again", onClick: retry }
          : { label: "Go to Downloads", href: "/downloads" }
      }
      secondaryAction={
        onRetry ? { label: "Go to Downloads", href: "/downloads" } : undefined
      }
      className={className}
    />
  );
}
