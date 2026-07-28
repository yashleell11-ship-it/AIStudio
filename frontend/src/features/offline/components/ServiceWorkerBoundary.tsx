"use client";

import { useCallback, useEffect, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  applyWorkerUpdate,
  publishScope,
  registerOfflineWorker,
  sweepOffline,
} from "../client";
import { useStorageScope, useWorkerUpdate } from "../hooks";

/**
 * How often launch/resume housekeeping may actually run. Coming back to the tab
 * every thirty seconds should not re-sweep every time; the 2-day timer does not
 * care about the difference.
 */
const HOUSEKEEPING_INTERVAL_MS = 5 * 60_000;

/**
 * Registers the service worker, keeps it told which profile is looking, and
 * runs the retention sweep when the app is opened or comes back to the front.
 *
 * Mounted from the root layout inside `Providers`, so `setStorageScope` has
 * already published the active (user, profile) by the time this reacts to it.
 *
 * The sweep runs on launch and resume and NEVER on a timer. A page that is
 * closed has no timer, so "deleted after 2 days" can only honestly mean "the
 * first time you open the app after 2 days" — the same promise
 * docs/OFFLINE_READING.md makes for the phone, for the same reason.
 */
export function ServiceWorkerBoundary() {
  const scope = useStorageScope();
  const lastHousekeepingRef = useRef(0);

  useEffect(() => {
    void registerOfflineWorker();
  }, []);

  // Publish the scope on mount and on every profile switch. A switch to "no
  // profile" publishes null, which stops the worker serving saved content
  // rather than leaving the previous profile's caches live.
  useEffect(() => {
    void publishScope(scope);
  }, [scope]);

  const runHousekeeping = useCallback(
    (force: boolean) => {
      if (!scope) return;
      const now = Date.now();
      if (!force && now - lastHousekeepingRef.current < HOUSEKEEPING_INTERVAL_MS) return;
      lastHousekeepingRef.current = now;
      void sweepOffline(scope, null);
      // Same moment is the right moment to look for a new build: the app was
      // just brought to the front, so a prompt now is not interrupting reading.
      void registerOfflineWorker().then((registration) => registration?.update());
    },
    [scope],
  );

  useEffect(() => {
    runHousekeeping(true);
    const onVisibility = () => {
      if (document.visibilityState === "visible") runHousekeeping(false);
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [runHousekeeping]);

  return <UpdatePrompt />;
}

/**
 * Offers the swap to a newly installed worker.
 *
 * Deliberately a prompt and not an automatic reload: the new worker controls
 * which bundle every subsequent request gets, and taking that decision away
 * from someone mid-chapter is how a reader loses their place.
 */
function UpdatePrompt() {
  const { waiting } = useWorkerUpdate();
  if (!waiting) return null;

  return (
    <div
      className={cn(
        "fixed bottom-4 left-1/2 z-50 -translate-x-1/2 px-4",
        "pb-[env(safe-area-inset-bottom)]",
      )}
      role="status"
    >
      <div className="glass-panel flex items-center gap-3 rounded-2xl px-4 py-3 shadow-glass">
        <RefreshCw className="size-4 shrink-0 text-primary" aria-hidden />
        <span className="text-sm text-fg">A new version is ready.</span>
        <button
          type="button"
          onClick={() => void applyWorkerUpdate(waiting)}
          className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-fg transition-colors hover:bg-primary-hover"
        >
          Reload
        </button>
      </div>
    </div>
  );
}
