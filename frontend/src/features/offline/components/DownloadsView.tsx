"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  CloudOff,
  HardDrive,
  Loader2,
  RotateCcw,
  ShieldCheck,
  Trash2,
  TriangleAlert,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Progress } from "@/components/ui/progress";
import { FadeIn } from "@/components/premium/FadeIn";
import { GlassPanel } from "@/components/premium/GlassPanel";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";
import { readerChapterHref, seriesPageHref } from "@/features/reader/reader-link";
import {
  clearOfflineScope,
  refreshOfflineState,
  removeSavedChapter,
  requestPersistentStorage,
  resetServiceWorker,
  setOfflineRetention,
} from "../client";
import { useNow, useOfflineState, useOnlineStatus, useStorageScope } from "../hooks";
import {
  describeEntry,
  expiryDueAt,
  formatBytes,
  formatDueIn,
  groupBySeries,
  savePercent,
  summariseStorage,
} from "../format";
import type { SavedChapterEntry } from "../types";

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * How long a finished chapter's copy survives. The owner's decision is 2 days
 * (docs/OFFLINE_READING.md); the constant is surfaced here so it can be changed
 * or turned off without a rebuild, which is the other half of that decision.
 */
const RETENTION_OPTIONS: { label: string; value: number | null }[] = [
  { label: "2 days", value: 2 * DAY_MS },
  { label: "7 days", value: 7 * DAY_MS },
  { label: "30 days", value: 30 * DAY_MS },
  { label: "Never", value: null },
];

/**
 * Saved chapters, what they cost, and how to get rid of them.
 *
 * Everything on this screen is read from the service worker's index for the
 * ACTIVE profile only. There is no view of another profile's downloads, from
 * here or from anywhere: they are in a cache this page never names.
 */
export function DownloadsView() {
  const scope = useStorageScope();
  const state = useOfflineState();
  const online = useOnlineStatus();
  const [persisted, setPersisted] = useState<boolean | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [busySeries, setBusySeries] = useState<string | null>(null);
  const [confirmSeries, setConfirmSeries] = useState<string | null>(null);
  // 0 until the clock is subscribed, which hides a countdown for one frame
  // rather than rendering one computed from a server-side timestamp.
  const now = useNow();

  useEffect(() => {
    void refreshOfflineState();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined" || !window.navigator.storage?.persisted) return;
    void window.navigator.storage.persisted().then(setPersisted);
  }, [state.entries.length]);

  const handleRemove = useCallback(
    async (key: string) => {
      if (!scope) return;
      setBusyKey(key);
      try {
        await removeSavedChapter(scope, key);
      } finally {
        setBusyKey(null);
      }
    },
    [scope],
  );

  /**
   * Free a whole series at once.
   *
   * The unit a reader thinks in changed when downloading did: picking "all
   * unread" on a series page stores twenty chapters in one action, and undoing
   * that one trash icon at a time is not an undo. Removal still goes through
   * the worker per chapter — it is the only writer of Cache Storage — so this
   * is a loop, not a new message.
   */
  const handleRemoveSeries = useCallback(
    async (entries: SavedChapterEntry[]) => {
      if (!scope) return;
      setBusySeries(entries[0]?.key ?? null);
      try {
        for (const entry of entries) {
          await removeSavedChapter(scope, entry.key);
        }
      } finally {
        setBusySeries(null);
      }
    },
    [scope],
  );

  const handleClearAll = useCallback(async () => {
    if (!scope) return;
    setConfirmClear(false);
    await clearOfflineScope(scope);
    await refreshOfflineState();
  }, [scope]);

  const handlePersist = useCallback(async () => {
    setPersisted(await requestPersistentStorage());
  }, []);

  const summary = summariseStorage(state.entries, state.estimate);
  const groups = groupBySeries(state.entries);

  return (
    <div className="page-shell bg-bg">
      <div className="page-container mx-auto max-w-4xl">
        <FadeIn className="mb-8" y={20}>
          <p className="mb-2 text-xs font-medium uppercase tracking-widest text-muted">
            On this device
          </p>
          <HeroHeading className="leading-none md:text-6xl">
            Downloads
          </HeroHeading>
          <p className="mt-3 max-w-xl text-sm text-muted">
            Chapters downloaded here are stored in this browser and open with no
            connection at all. They belong to the profile that downloaded them.
          </p>
          {!online ? (
            <p className="mt-3 inline-flex items-center gap-2 rounded-full border border-border/60 bg-surface px-3 py-1 text-xs text-muted">
              <WifiOff className="size-3.5 text-warning" aria-hidden />
              You are offline — only saved chapters will open.
            </p>
          ) : null}
        </FadeIn>

        {state.readiness === "unsupported" ? (
          <EmptyState
            tone="error"
            icon={TriangleAlert}
            title="Downloads are unavailable here"
            description="This browser has no service worker, or the page is not being served over a secure connection. Both are required to store chapters on the device."
          />
        ) : !scope ? (
          <EmptyState
            icon={CloudOff}
            title="No profile selected"
            description="Downloaded chapters belong to a reading profile. Choose one and its downloads appear here."
          />
        ) : (
          <>
            <FadeIn y={20} delay={0.05}>
              <GlassPanel className="mb-6 p-5 md:p-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-primary/15 text-primary">
                      <HardDrive className="size-5" aria-hidden />
                    </div>
                    <div>
                      <p className="font-display text-lg tracking-wide text-fg">
                        {formatBytes(summary.chapterBytes)} in {summary.chapterCount}{" "}
                        {summary.chapterCount === 1 ? "chapter" : "chapters"}
                      </p>
                      <p className="mt-0.5 text-sm text-muted">
                        {summary.percentUsed === null
                          ? "This browser does not report a storage quota."
                          : `${formatBytes(summary.usage)} of ${formatBytes(
                              summary.quota,
                            )} used by this site · ${formatBytes(
                              summary.free ?? 0,
                            )} free`}
                      </p>
                    </div>
                  </div>
                  {persisted === true ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success/10 px-3 py-1 text-xs text-success">
                      <ShieldCheck className="size-3.5" aria-hidden />
                      Storage protected
                    </span>
                  ) : persisted === false ? (
                    <Button variant="secondary" size="sm" onClick={() => void handlePersist()}>
                      Ask to protect storage
                    </Button>
                  ) : null}
                </div>

                {summary.percentUsed !== null ? (
                  <div className="mt-4">
                    <Progress
                      value={summary.percentUsed}
                      variant="gradient"
                      aria-label="Storage used by this site"
                    />
                    <p className="mt-2 text-xs text-muted">
                      Saving stops before the last 250 MB of the quota. When it gets
                      close, finished chapters are removed oldest-first — never one you
                      have not read, and never the one you have open.
                    </p>
                  </div>
                ) : null}
              </GlassPanel>
            </FadeIn>

            <FadeIn y={20} delay={0.1}>
              <GlassPanel className="mb-6 p-5 md:p-6">
                <h2 className="font-display text-lg tracking-wide text-fg">
                  Delete finished chapters after
                </h2>
                <p className="mt-1 text-sm text-muted">
                  A chapter starts its timer when you finish it, and the timer is
                  cancelled if you open it again. The sweep runs when you open the app,
                  not in the background — a closed tab has no timers.
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {RETENTION_OPTIONS.map((option) => {
                    const active = (state.retentionMs ?? null) === option.value;
                    return (
                      <button
                        key={option.label}
                        type="button"
                        onClick={() => void setOfflineRetention(scope, option.value)}
                        aria-pressed={active}
                        className={cn(
                          "rounded-xl border px-3 py-1.5 text-sm transition-colors",
                          active
                            ? "border-primary/40 bg-primary/15 text-primary"
                            : "border-border/60 bg-white/[0.03] text-muted hover:text-fg",
                        )}
                      >
                        {option.label}
                      </button>
                    );
                  })}
                </div>
              </GlassPanel>
            </FadeIn>

            {state.readiness === "pending" ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted">
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Checking what is stored…
              </div>
            ) : groups.length === 0 ? (
              <EmptyState
                icon={CloudOff}
                title="Nothing downloaded yet"
                description={
                  <>
                    Pick chapters on a series page and press{" "}
                    <span className="text-primary">Download</span>, or press it in
                    the reader for the chapter you have open. What you save is
                    stored here and stays readable with no connection.
                  </>
                }
                action={{ label: "Go to library", href: "/library" }}
              />
            ) : (
              <FadeIn y={20} delay={0.15} className="space-y-4">
                {groups.map((group) => (
                  <GlassPanel key={group.id} className="overflow-hidden">
                    <div className="flex items-center justify-between gap-3 border-b border-border/60 px-5 py-3">
                      <Link
                        href={seriesPageHref({
                          sourceId: group.sourceId,
                          seriesKey: group.seriesKey,
                        })}
                        className="min-w-0 truncate font-medium text-fg transition-colors hover:text-primary"
                      >
                        {group.seriesTitle}
                      </Link>
                      <div className="flex shrink-0 items-center gap-3">
                        <span className="font-mono text-xs tabular-nums text-muted">
                          {formatBytes(group.bytes)}
                        </span>
                        <button
                          type="button"
                          disabled={busySeries === group.entries[0]?.key}
                          onClick={() =>
                            confirmSeries === group.id
                              ? void handleRemoveSeries(group.entries).then(() =>
                                  setConfirmSeries(null),
                                )
                              : setConfirmSeries(group.id)
                          }
                          className={cn(
                            "rounded-lg px-2 py-1 text-xs transition-colors disabled:opacity-40",
                            confirmSeries === group.id
                              ? "bg-danger/10 text-danger"
                              : "text-muted hover:text-fg",
                          )}
                        >
                          {busySeries === group.entries[0]?.key
                            ? "Removing…"
                            : confirmSeries === group.id
                              ? `Remove all ${group.entries.length}?`
                              : "Remove series"}
                        </button>
                      </div>
                    </div>
                    <ul>
                      {group.entries.map((entry) => (
                        <SavedChapterRow
                          key={entry.key}
                          entry={entry}
                          retentionMs={state.retentionMs}
                          now={now}
                          busy={busyKey === entry.key}
                          openKey={state.openChapterKey}
                          onRemove={() => void handleRemove(entry.key)}
                        />
                      ))}
                    </ul>
                  </GlassPanel>
                ))}
              </FadeIn>
            )}

            <FadeIn y={20} delay={0.2}>
              <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-border/60 pt-6">
                <Button
                  variant={confirmClear ? "danger" : "secondary"}
                  size="sm"
                  disabled={state.entries.length === 0}
                  onClick={() =>
                    confirmClear ? void handleClearAll() : setConfirmClear(true)
                  }
                >
                  <Trash2 className="size-4" aria-hidden />
                  {confirmClear ? "Delete everything saved?" : "Remove all downloads"}
                </Button>
                <Button variant="ghost" size="sm" onClick={() => void resetServiceWorker()}>
                  <RotateCcw className="size-4" aria-hidden />
                  Reset offline storage
                </Button>
                <p className="text-xs text-muted">
                  Resetting unregisters the offline worker and clears every cache — the
                  way out if the app ever gets stuck on an old version.
                </p>
              </div>
            </FadeIn>
          </>
        )}
      </div>
    </div>
  );
}

function SavedChapterRow({
  entry,
  retentionMs,
  now,
  busy,
  openKey,
  onRemove,
}: {
  entry: SavedChapterEntry;
  retentionMs: number | null;
  now: number;
  busy: boolean;
  openKey: string | null;
  onRemove: () => void;
}) {
  const description = describeEntry(entry);
  const dueAt = expiryDueAt(entry, retentionMs);
  const percent = savePercent(entry);

  return (
    <li className="flex items-center gap-3 border-b border-border/40 px-5 py-3 last:border-b-0">
      <div className="min-w-0 flex-1">
        <Link
          href={readerChapterHref({
            sourceId: entry.sourceId,
            seriesKey: entry.seriesKey,
            chapterKey: entry.chapterKey,
          })}
          className="block truncate text-sm text-fg transition-colors hover:text-primary"
        >
          {entry.title}
        </Link>
        <p
          className={cn(
            "mt-0.5 truncate text-xs",
            description.tone === "warn"
              ? "text-warning"
              : description.tone === "busy"
                ? "text-primary"
                : "text-muted",
          )}
        >
          {description.label}
          {dueAt !== null && now > 0 ? ` · ${formatDueIn(dueAt, now)}` : ""}
          {entry.key === openKey ? " · open now, kept" : ""}
        </p>
        {entry.status === "saving" ? (
          <Progress value={percent} className="mt-2 h-1" aria-label="Saving progress" />
        ) : null}
      </div>
      <button
        type="button"
        onClick={onRemove}
        disabled={busy}
        aria-label={`Remove ${entry.title} from this device`}
        className="shrink-0 rounded-lg p-2 text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:opacity-40"
      >
        {busy ? (
          <Loader2 className="size-4 animate-spin" aria-hidden />
        ) : (
          <Trash2 className="size-4" aria-hidden />
        )}
      </button>
    </li>
  );
}
