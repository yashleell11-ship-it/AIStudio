"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { StorageScope } from "@/lib/scoped-storage";
import {
  cancelChapterSave,
  getOfflineSnapshot,
  saveChapterOffline,
  subscribeOffline,
} from "./client";
import {
  describeRun,
  runDownloadQueue,
  type DownloadProgress,
  type DownloadRun,
  type RunSummary,
  type SaveOutcome,
} from "./download-queue";
import { useOfflineState, useStorageScope } from "./hooks";
import type { SaveChapterRequest } from "./protocol";
import {
  chapterDownloadState,
  savedChaptersForSeries,
  seriesChapterKey,
  type ChapterDownloadState,
} from "./series-downloads";
import { summariseStorage } from "./format";
import type { SavedChapterEntry } from "./types";

/**
 * The page-side half of a multi-chapter download.
 *
 * Waiting for a chapter to SETTLE is the whole of the difficulty. The worker
 * answers `mm-offline/save-chapter` with `{ accepted: true }` before it fetches
 * anything, so the reply proves only that the message arrived — it says nothing
 * about whether the chapter is on the device, and a queue driven by it would
 * start all ten at once. The outcome only ever appears in the state the worker
 * broadcasts as it writes its index, so that is what is watched here.
 */

/** A terminal state we never saw as "saving" is accepted after this long. */
const SETTLE_GRACE_MS = 5_000;

/**
 * How long the worker may say nothing at all before a chapter is given up on.
 *
 * A save that is progressing broadcasts as it stores each page (throttled to
 * ~300ms), so silence this long means the worker was killed mid-save or the
 * message never reached it. The queue has to move on — but the chapter's row
 * keeps rendering the worker's own state, so if it does finish later it says
 * "Saved" regardless of what the run reported.
 */
const SETTLE_STALL_MS = 90_000;

function outcomeOf(entry: SavedChapterEntry): SaveOutcome {
  if (entry.status === "paused") return "paused";
  if (entry.status === "ready" && entry.savedPages >= entry.pageCount) return "saved";
  return "incomplete";
}

/**
 * Resolve once the worker stops working on `key`.
 *
 * MUST be armed before the save is dispatched: `subscribeOffline` registers
 * synchronously, and the worker's first broadcast cannot arrive before the
 * `postMessage` that follows.
 */
function watchSettle(key: string): { settled: Promise<SaveOutcome>; abandon: () => void } {
  let finish: (outcome: SaveOutcome) => void = () => {};
  let done = false;
  let seenSaving = false;
  let graceElapsed = false;
  let unsubscribe = () => {};
  let stallTimer = 0;
  let graceTimer = 0;

  const settled = new Promise<SaveOutcome>((resolve) => {
    finish = resolve;
  });

  const entryNow = (): SavedChapterEntry | null =>
    getOfflineSnapshot().entries.find((candidate) => candidate.key === key) ?? null;

  const stop = (outcome: SaveOutcome) => {
    if (done) return;
    done = true;
    unsubscribe();
    window.clearTimeout(stallTimer);
    window.clearTimeout(graceTimer);
    finish(outcome);
  };

  const armStall = () => {
    window.clearTimeout(stallTimer);
    stallTimer = window.setTimeout(() => stop("failed"), SETTLE_STALL_MS);
  };

  const check = () => {
    armStall();
    const entry = entryNow();
    if (!entry) return;
    if (entry.status === "saving") {
      seenSaving = true;
      return;
    }
    // Before the worker has claimed the chapter, a terminal state is last
    // run's, not this one's — except when there is nothing to do, which the
    // grace window is there to let through.
    if (seenSaving || graceElapsed) stop(outcomeOf(entry));
  };

  unsubscribe = subscribeOffline(check);
  armStall();
  graceTimer = window.setTimeout(() => {
    graceElapsed = true;
    check();
  }, SETTLE_GRACE_MS);

  return { settled, abandon: () => stop("failed") };
}

export interface SeriesDownloads {
  /** Null until a profile is known; nothing is savable without one. */
  scope: StorageScope | null;
  /** Downloads are impossible in this browser (no worker, or an insecure page). */
  unavailable: boolean;
  saved: ReadonlyMap<string, SavedChapterEntry>;
  stateOf: (chapterKey: string) => ChapterDownloadState;
  running: boolean;
  progress: DownloadProgress | null;
  summary: RunSummary | null;
  /** Chapter keys queued behind the one in flight. */
  pending: ReadonlySet<string>;
  download: (chapterKeys: readonly string[]) => Promise<DownloadRun | null>;
  cancel: () => void;
  dismissSummary: () => void;
}

export interface SeriesDownloadsInput {
  sourceId: string;
  seriesKey: string;
  /**
   * One chapter's download plan. Async because a manga chapter's page URLs come
   * from its manifest, which the series page does not hold. Returning null (or
   * throwing) counts the chapter as failed and the run carries on.
   */
  buildRequest: (chapterKey: string) => Promise<SaveChapterRequest | null>;
  /** Optional bulk warm; see `DownloadQueueDeps.prepare`. */
  prepare?: (upcoming: readonly string[]) => Promise<void>;
}

export function useSeriesDownloads({
  sourceId,
  seriesKey,
  buildRequest,
  prepare,
}: SeriesDownloadsInput): SeriesDownloads {
  const scope = useStorageScope();
  const state = useOfflineState();
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [pending, setPending] = useState<ReadonlySet<string>>(() => new Set<string>());
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef<string | null>(null);

  const saved = useMemo(
    () => savedChaptersForSeries(state.entries, { sourceId, seriesKey }),
    [state.entries, seriesKey, sourceId],
  );

  const stateOf = useCallback(
    (chapterKey: string): ChapterDownloadState => {
      if (pending.has(chapterKey)) return "queued";
      return chapterDownloadState(saved.get(chapterKey));
    },
    [pending, saved],
  );

  // A page torn down mid-run must not leave a queue running against a component
  // that no longer exists. The chapter already in the worker keeps going —
  // that is the point of saving there — but nothing new is started.
  useEffect(() => () => abortRef.current?.abort(), []);

  const download = useCallback(
    async (chapterKeys: readonly string[]): Promise<DownloadRun | null> => {
      if (!scope || chapterKeys.length === 0 || abortRef.current) return null;
      const controller = new AbortController();
      abortRef.current = controller;
      setSummary(null);
      setPending(new Set(chapterKeys));
      setProgress({ completed: 0, total: chapterKeys.length, current: null });

      const save = async (chapterKey: string): Promise<SaveOutcome> => {
        const cacheKey = seriesChapterKey({ sourceId, seriesKey }, chapterKey);
        let request: SaveChapterRequest | null;
        try {
          request = await buildRequest(chapterKey);
        } catch {
          return "failed";
        }
        if (!request) return "failed";

        const watcher = watchSettle(cacheKey);
        inFlightRef.current = cacheKey;
        const reply = await saveChapterOffline(request);
        if (!reply.ok) {
          watcher.abandon();
          inFlightRef.current = null;
          return "failed";
        }
        const outcome = await watcher.settled;
        inFlightRef.current = null;
        return outcome;
      };

      try {
        const run = await runDownloadQueue(chapterKeys, {
          save,
          prepare,
          signal: controller.signal,
          onProgress: (next) => {
            setProgress(next);
            // "Queued" is everything after the chapter having its turn; the one
            // in flight drops out so its row shows the worker's own progress.
            const started = next.current !== null ? next.completed + 1 : next.completed;
            setPending(new Set(chapterKeys.slice(started)));
          },
        });
        const snapshot = getOfflineSnapshot();
        setSummary(
          describeRun(run, summariseStorage(snapshot.entries, snapshot.estimate).free),
        );
        return run;
      } finally {
        abortRef.current = null;
        inFlightRef.current = null;
        setProgress(null);
        setPending(new Set<string>());
      }
    },
    [buildRequest, prepare, scope, seriesKey, sourceId],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    // Abort only stops the NEXT chapter; the one already in the worker has to
    // be told directly, or "Stop" would sit there downloading a 200-page
    // chapter it had just been told to stop downloading.
    if (inFlightRef.current) void cancelChapterSave(inFlightRef.current);
  }, []);

  return {
    scope,
    unavailable: state.readiness === "unsupported",
    saved,
    stateOf,
    running: progress !== null,
    progress,
    summary,
    pending,
    download,
    cancel,
    dismissSummary: () => setSummary(null),
  };
}
