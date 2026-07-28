"use client";

import { useState } from "react";
import Image from "next/image";
import { ArrowLeftRight, ImageOff, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { SourceLogo } from "@/features/sources/components/SourceLogo";
import { ApiError } from "@/types/api";
import { cn } from "@/lib/cn";
import { useMigrateTracker, useMigrationCandidates } from "../hooks";
import {
  migrationConflictTrackerId,
  migrationSummary,
  parseChapterOffset,
  stalePreviewFromError,
} from "../migration";
import type { MigrationCandidate, MigrationPlan, SeriesTracker } from "../types";

interface MigrateSeriesDialogProps {
  tracker: SeriesTracker;
  onClose: () => void;
}

/** How many mappings to spell out before falling back to the counts. */
const MAPPING_PREVIEW_ROWS = 12;

const MATCH_LABEL: Record<string, string> = {
  exact: "exact",
  nearest: "nearest",
  none: "no equivalent",
};

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof ApiError ? cause.message : fallback;
}

function CandidateRow({
  candidate,
  disabled,
  onPreview,
}: {
  candidate: MigrationCandidate;
  disabled: boolean;
  onPreview: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border/40 bg-white/[0.02] p-3">
      <div className="relative h-16 w-11 shrink-0 overflow-hidden rounded-md bg-surface-2">
        {candidate.cover_url ? (
          <Image
            src={candidate.cover_url}
            alt=""
            fill
            className="object-cover"
            sizes="44px"
            unoptimized
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-muted/40">
            <ImageOff className="size-4" aria-hidden />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-fg">{candidate.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
          <SourceLogo
            id={candidate.source}
            name={candidate.source_name ?? candidate.source}
            iconUrl={candidate.icon_url}
            size={24}
            className="rounded-lg"
          />
          <span>{candidate.source_name ?? candidate.source}</span>
          {candidate.chapter_count ? <span>· {candidate.chapter_count} chapters</span> : null}
        </div>
      </div>
      <Button size="sm" variant="secondary" disabled={disabled} onClick={onPreview}>
        Preview
      </Button>
    </div>
  );
}

function PlanPreview({ plan }: { plan: MigrationPlan }) {
  const rows = plan.chapter_map.slice(0, MAPPING_PREVIEW_ROWS);
  const hidden = plan.chapter_map.length - rows.length;

  return (
    <div className="space-y-3">
      <p className="text-sm text-fg/90">{migrationSummary(plan.counts)}</p>

      {plan.warnings.map((warning) => (
        <div
          key={warning}
          className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-fg/90"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <span>{warning}</span>
        </div>
      ))}

      {rows.length > 0 ? (
        <div className="max-h-56 overflow-y-auto rounded-xl border border-border/40">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface-2/90 text-muted backdrop-blur-sm">
              <tr>
                <th className="px-3 py-2 font-medium">Chapter</th>
                <th className="px-3 py-2 font-medium">On the target</th>
                <th className="px-3 py-2 font-medium">Match</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {rows.map((entry) => (
                <tr key={entry.from_chapter_id}>
                  <td className="px-3 py-1.5 tabular-nums text-fg/90">
                    {entry.number ?? "—"}
                  </td>
                  <td
                    className={cn(
                      "max-w-[12rem] truncate px-3 py-1.5",
                      entry.to_chapter_id ? "text-fg/80" : "text-muted",
                    )}
                  >
                    {entry.to_chapter_id ?? "—"}
                  </td>
                  <td
                    className={cn(
                      "px-3 py-1.5",
                      entry.match === "none" ? "text-danger" : "text-muted",
                    )}
                  >
                    {MATCH_LABEL[entry.match] ?? entry.match}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted">
          There is nothing to remap — the follow will simply be repointed.
        </p>
      )}

      {hidden > 0 ? (
        <p className="text-xs text-muted">
          Showing the first {rows.length} of {plan.chapter_map.length} chapters.
        </p>
      ) : null}
    </div>
  );
}

/**
 * Move a followed series to another source, keeping reading progress.
 *
 * The endpoint's dry run is what makes this safe to offer: the mapping shown
 * here is computed by the same code path as the commit, so the user confirms
 * the exact remap that will be applied — and the commit is refused outright if
 * the target's chapter list changed in between.
 *
 * Mounted only while open (callers render it conditionally), so reopening
 * always starts a fresh migration: a preview left over from last time would be
 * confirmable against a chapter list nobody looked at.
 */
export function MigrateSeriesDialog({ tracker, onClose }: MigrateSeriesDialogProps) {
  const [query, setQuery] = useState(tracker.series_title);
  const [submittedQuery, setSubmittedQuery] = useState(tracker.series_title);
  const [selected, setSelected] = useState<MigrationCandidate | null>(null);
  const [offset, setOffset] = useState("0");
  const [plan, setPlan] = useState<MigrationPlan | null>(null);
  const [applied, setApplied] = useState<MigrationPlan | null>(null);
  const [conflictTrackerId, setConflictTrackerId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const candidates = useMigrationCandidates(
    tracker.id,
    submittedQuery,
    plan === null && applied === null,
  );
  const migrate = useMigrateTracker();

  const preview = async (candidate: MigrationCandidate) => {
    const chapterOffset = parseChapterOffset(offset);
    if (chapterOffset === null) {
      setError("Chapter offset must be a number.");
      return;
    }
    setError(null);
    setConflictTrackerId(null);
    try {
      const next = await migrate.mutateAsync({
        trackerId: tracker.id,
        body: {
          target_source: candidate.source,
          target_series_id: candidate.series_id,
          target_series_title: candidate.title,
          chapter_offset: chapterOffset,
          dry_run: true,
        },
      });
      setSelected(candidate);
      setPlan(next);
    } catch (cause) {
      setError(errorMessage(cause, "Could not read the target's chapter list."));
    }
  };

  const confirm = async (merge: boolean) => {
    if (!selected || !plan) return;
    const chapterOffset = parseChapterOffset(offset);
    if (chapterOffset === null) {
      setError("Chapter offset must be a number.");
      return;
    }
    setError(null);
    try {
      const next = await migrate.mutateAsync({
        trackerId: tracker.id,
        body: {
          target_source: selected.source,
          target_series_id: selected.series_id,
          target_series_title: selected.title,
          chapter_offset: chapterOffset,
          dry_run: false,
          merge,
          expected_chapter_map_hash: plan.chapter_map_hash,
        },
      });
      setApplied(next);
      setConflictTrackerId(null);
    } catch (cause) {
      const stale = stalePreviewFromError(cause);
      if (stale) {
        setPlan(stale);
        setError(
          "The target's chapter list changed since this preview. Review the updated mapping and confirm again.",
        );
        return;
      }
      const conflict = migrationConflictTrackerId(cause);
      if (conflict !== null) {
        setConflictTrackerId(conflict);
        setError(errorMessage(cause, "You already follow that series on that source."));
        return;
      }
      setError(errorMessage(cause, "The migration could not be completed."));
    }
  };

  const busy = migrate.isPending;

  return (
    <Dialog
      open
      onClose={onClose}
      title="Move to another source"
      // Wider and scrollable than the default panel: the candidate list runs to
      // one row per source and the mapping table needs three columns.
      className="max-h-[85vh] max-w-2xl overflow-y-auto"
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
          <span className="font-medium text-fg">{tracker.series_title}</span>
          <Badge variant="default">{tracker.source}</Badge>
          {selected ? (
            <>
              <ArrowLeftRight className="size-4" aria-hidden />
              <Badge variant="primary">{selected.source}</Badge>
            </>
          ) : null}
        </div>

        {error ? (
          <div className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {error}
          </div>
        ) : null}

        {applied ? (
          <div className="space-y-3">
            <p className="text-sm text-fg/90">
              Moved to {applied.to.source}. {migrationSummary(applied.counts)}.
            </p>
            <p className="text-xs text-muted">
              {applied.notifications_rewritten} notification(s) repointed,{" "}
              {applied.notifications_dropped} dropped, {applied.downloads_relinked}{" "}
              downloaded chapter(s) relinked
              {applied.merged_into_tracker_id !== null
                ? `, merged into follow #${applied.merged_into_tracker_id}`
                : ""}
              .
            </p>
            <div className="flex justify-end">
              <Button onClick={onClose}>Done</Button>
            </div>
          </div>
        ) : plan && selected ? (
          <div className="space-y-4">
            <PlanPreview plan={plan} />

            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-muted">
                Chapter offset
                <Input
                  value={offset}
                  onChange={(event) => setOffset(event.target.value)}
                  inputMode="decimal"
                  className="h-9 w-28"
                  aria-label="Chapter offset"
                />
              </label>
              <Button
                variant="secondary"
                size="sm"
                disabled={busy}
                onClick={() => void preview(selected)}
              >
                Recalculate
              </Button>
              <p className="w-full text-xs text-muted">
                Added to every old chapter number before matching, for targets that
                restart numbering per season. Nudge it until the mapped count peaks.
              </p>
            </div>

            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setPlan(null);
                  setSelected(null);
                  setConflictTrackerId(null);
                  setError(null);
                }}
              >
                Back
              </Button>
              {conflictTrackerId !== null ? (
                <Button variant="danger" disabled={busy} onClick={() => void confirm(true)}>
                  Merge the two follows
                </Button>
              ) : (
                <Button disabled={busy} onClick={() => void confirm(false)}>
                  {busy ? "Moving…" : "Move this series"}
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <form
              className="flex gap-2"
              onSubmit={(event) => {
                event.preventDefault();
                setSubmittedQuery(query.trim());
              }}
            >
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search other sources"
                aria-label="Search other sources"
              />
              <Button type="submit" variant="secondary" disabled={candidates.isFetching}>
                Search
              </Button>
            </form>

            {candidates.isLoading ? (
              <div className="space-y-2" aria-busy="true">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div key={index} className="h-[88px] animate-pulse rounded-xl bg-surface-2" />
                ))}
              </div>
            ) : candidates.error ? (
              <div className="space-y-2">
                <p className="text-sm text-danger">
                  {errorMessage(candidates.error, "Failed to look for other sources.")}
                </p>
                <Button variant="secondary" size="sm" onClick={() => candidates.refetch()}>
                  Try again
                </Button>
              </div>
            ) : (candidates.data?.candidates.length ?? 0) === 0 ? (
              <p className="text-sm text-muted">
                No other source has a match for this title. Try a different search term.
              </p>
            ) : (
              <>
                <div className="space-y-2">
                  {candidates.data?.candidates.map((candidate) => (
                    <CandidateRow
                      key={`${candidate.source}:${candidate.series_id}`}
                      candidate={candidate}
                      disabled={busy}
                      onPreview={() => void preview(candidate)}
                    />
                  ))}
                </div>
                <p className="text-xs text-muted">
                  Searched {candidates.data?.sources_queried ?? 0} sources
                  {(candidates.data?.sources_failed ?? 0) > 0
                    ? ` (${candidates.data?.sources_failed} did not answer — normal on a registry this size)`
                    : ""}
                  .
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </Dialog>
  );
}
