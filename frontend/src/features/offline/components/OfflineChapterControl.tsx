"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Check, CloudDownload, Loader2, TriangleAlert, X } from "lucide-react";
import { cn } from "@/lib/cn";
import { readerChapterQueryKey } from "@/features/reader/hooks";
import type { ReaderChapterContent } from "@/features/reader/types";
import {
  cancelChapterSave,
  markChapterClosed,
  markChapterFinished,
  markChapterOpened,
  removeSavedChapter,
  resolveApiBase,
  saveChapterOffline,
} from "../client";
import { useOfflineState, useSavedChapter, useStorageScope } from "../hooks";
import { describeEntry, savePercent } from "../format";
import { buildSaveRequest, chapterCacheKey, isSavableChapter } from "../save-request";

interface OfflineChapterControlProps {
  chapter: ReaderChapterContent;
  /** The page the reader is on, used to notice the chapter being finished. */
  visiblePage: number;
  /** Follows the reader's own chrome so the strip stays uncluttered. */
  visible: boolean;
}

/** How long the confirm state stays armed before reverting. */
const CONFIRM_TIMEOUT_MS = 4_000;

/**
 * "Save for offline", in the reader, for the chapter on screen.
 *
 * It hooks into the reader at the one seam that matters: the page URLs the
 * reader already resolved. Those exact URLs are handed to the worker, which
 * stores the responses under them, so when the network is gone the same
 * `<img src>` the reader has always rendered is answered from the cache with no
 * change to how the reader loads a page. Nothing about page resolution moves.
 *
 * It also owns the read lifecycle for the chapter it is showing, because it is
 * the only component that knows both "which chapter" and "which page":
 *   - opened   → cancels any pending 2-day deletion and protects it from
 *                eviction while it is on screen
 *   - finished → starts the 2-day timer
 *   - closed   → releases the protection
 */
export function OfflineChapterControl({
  chapter,
  visiblePage,
  visible,
}: OfflineChapterControlProps) {
  const scope = useStorageScope();
  const state = useOfflineState();
  const queryClient = useQueryClient();
  const key = chapterCacheKey(chapter.id);
  const entry = useSavedChapter(key);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);
  const finishedRef = useRef(false);

  const savable = isSavableChapter(chapter);

  // Opening a chapter cancels its expiry; leaving releases the eviction guard.
  useEffect(() => {
    if (!scope || !savable) return;
    finishedRef.current = false;
    void markChapterOpened(scope, key);
    return () => {
      void markChapterClosed(key);
    };
  }, [key, savable, scope]);

  // Finishing starts the 2-day timer. Reported once per visit: the reader sits
  // on the last page while the reader reads it, and re-stamping on every scroll
  // event would be a message per frame.
  useEffect(() => {
    if (!scope || !entry || finishedRef.current) return;
    if (chapter.pages.length === 0 || visiblePage < chapter.pages.length) return;
    finishedRef.current = true;
    void markChapterFinished(scope, key);
  }, [chapter.pages.length, entry, key, scope, visiblePage]);

  useEffect(() => {
    if (!confirmRemove) return;
    const timer = window.setTimeout(() => setConfirmRemove(false), CONFIRM_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [confirmRemove]);

  const handleSave = useCallback(async () => {
    if (!scope) return;
    setBusy(true);
    try {
      // The payload the reader is already rendering from, so the saved copy and
      // the saved images are guaranteed to describe the same pages. When it is
      // not in the cache the worker fetches it itself — `payloadUrl` is in the
      // download plan either way.
      const cached = queryClient.getQueryData(readerChapterQueryKey(Number(chapter.id)));
      await saveChapterOffline(
        buildSaveRequest({
          chapter,
          scope,
          apiBase: resolveApiBase(),
          origin: window.location.origin,
          payloadJson: cached ? JSON.stringify(cached) : null,
        }),
      );
    } finally {
      setBusy(false);
    }
  }, [chapter, queryClient, scope]);

  const handleRemove = useCallback(async () => {
    if (!scope) return;
    setConfirmRemove(false);
    setBusy(true);
    try {
      await removeSavedChapter(scope, key);
    } finally {
      setBusy(false);
    }
  }, [key, scope]);

  // Nothing to offer: an online-source chapter cannot be stored (its pages are
  // opaque cross-origin bytes), no profile means no cache to store it in, and a
  // browser without a worker has nowhere to put it.
  if (!savable || !scope) return null;
  if (state.readiness === "unsupported") return null;

  const saving = entry?.status === "saving";
  const percent = entry ? savePercent(entry) : 0;
  const description = entry ? describeEntry(entry) : null;

  return (
    <div
      className={cn(
        "fixed right-4 top-4 z-30 transition-opacity duration-300",
        visible ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      {saving ? (
        <button
          type="button"
          onClick={() => void cancelChapterSave(key)}
          className="glass-panel flex items-center gap-2 rounded-full px-3 py-1.5 text-xs text-fg transition-colors hover:border-danger/40"
          title="Stop saving this chapter"
        >
          <Loader2 className="size-3.5 animate-spin text-primary" aria-hidden />
          <span className="font-mono tabular-nums">
            {entry?.savedPages ?? 0}/{entry?.pageCount ?? chapter.pages.length}
          </span>
          <span className="text-muted">·</span>
          <span className="text-muted">{percent}%</span>
          <X className="size-3.5 text-muted" aria-hidden />
          <span className="sr-only">Cancel saving this chapter for offline reading</span>
        </button>
      ) : entry && description?.tone === "warn" ? (
        // Incomplete, paused or stale. The useful action here is to fix it, not
        // to delete it — a chapter with holes is repaired by saving again, and
        // the pages already stored are skipped. Deleting lives on /offline.
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleSave()}
          className="glass-panel flex items-center gap-2 rounded-full px-3 py-1.5 text-xs text-warning transition-colors hover:border-warning/40 disabled:opacity-50"
          title={description.label}
        >
          <TriangleAlert className="size-3.5" aria-hidden />
          {entry.stale ? "Save again" : `Resume ${entry.savedPages}/${entry.pageCount}`}
        </button>
      ) : entry ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => (confirmRemove ? void handleRemove() : setConfirmRemove(true))}
          className={cn(
            "glass-panel flex items-center gap-2 rounded-full px-3 py-1.5 text-xs transition-colors",
            confirmRemove
              ? "border-danger/50 text-danger"
              : "text-fg hover:border-primary/40",
          )}
          title={description?.label}
        >
          {confirmRemove ? (
            <>
              <X className="size-3.5" aria-hidden />
              Remove download?
            </>
          ) : (
            <>
              <Check className="size-3.5 text-success" aria-hidden />
              Saved
            </>
          )}
        </button>
      ) : (
        <button
          type="button"
          disabled={busy || state.readiness === "pending"}
          onClick={() => void handleSave()}
          className="glass-panel flex items-center gap-2 rounded-full px-3 py-1.5 text-xs text-fg transition-colors hover:border-primary/40 hover:text-primary disabled:opacity-50"
        >
          <CloudDownload className="size-3.5" aria-hidden />
          Save for offline
        </button>
      )}
    </div>
  );
}
