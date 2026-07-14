"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, RefreshCw, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import {
  useCancelOcrJob,
  useOcrJobs,
  useOcrMetrics,
  useOcrSearch,
  useRetryOcrJob,
} from "../hooks";
import { parseSnippet } from "../snippet";
import type { OcrJob, OcrJobStatus, OcrSearchResultItem } from "../types";

const SEARCH_DEBOUNCE_MS = 300;

function jobStatusClasses(status: OcrJobStatus): string {
  switch (status) {
    case "completed":
      return "border-success/40 bg-success/15 text-success";
    case "processing":
      return "border-primary/40 bg-primary/15 text-primary";
    case "failed":
      return "border-danger/40 bg-danger/15 text-danger";
    case "cancelled":
      return "border-warning/40 bg-warning/15 text-warning";
    case "queued":
    default:
      return "border-border/50 bg-surface text-muted";
  }
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export function OcrSearchView() {
  return (
    <div className="page-shell">
      <div className="page-container space-y-8">
        <header>
          <HeroHeading className="text-[2.75rem] leading-none md:text-6xl">
            OCR Search
          </HeroHeading>
          <p className="mt-2 text-sm text-muted">
            Search extracted dialogue across your library and monitor the OCR queue.
          </p>
        </header>

        <DialogueSearch />
        <QueueStatus />
      </div>
    </div>
  );
}

function DialogueSearch() {
  const [rawQuery, setRawQuery] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => setQuery(rawQuery), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [rawQuery]);

  const { data, isFetching, isError, error } = useOcrSearch(query);
  const trimmed = query.trim();
  const results = data?.items ?? [];

  return (
    <section className="space-y-4" aria-labelledby="ocr-search-heading">
      <h2 id="ocr-search-heading" className="text-sm font-medium text-muted">
        Dialogue search
      </h2>

      <div className="relative">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <Input
          type="search"
          value={rawQuery}
          onChange={(event) => setRawQuery(event.target.value)}
          placeholder="Search dialogue, e.g. “I will protect you”"
          aria-label="Search extracted dialogue"
          className="pl-9"
        />
        {isFetching ? (
          <Loader2
            className="absolute right-3 top-1/2 size-4 -translate-y-1/2 animate-spin text-muted"
            aria-hidden
          />
        ) : null}
      </div>

      {isError ? (
        <p className="text-sm text-danger">{errorMessage(error)}</p>
      ) : !trimmed ? (
        <p className="text-sm text-muted">
          Type at least one word to search text extracted from your chapters.
        </p>
      ) : data && results.length === 0 ? (
        <p className="text-sm text-muted">No dialogue matches “{trimmed}”.</p>
      ) : (
        <ul className="space-y-2">
          {results.map((item) => (
            <SearchResult key={item.chapter_id} item={item} />
          ))}
        </ul>
      )}

      {data && data.has_more ? (
        <p className="text-xs text-muted">
          Showing the first {results.length} of {data.total} matches. Refine your query to narrow results.
        </p>
      ) : null}
    </section>
  );
}

function SearchResult({ item }: { item: OcrSearchResultItem }) {
  const segments = parseSnippet(item.snippet);
  return (
    <li className="rounded-xl border border-border/50 bg-surface-2 p-4">
      <Link
        href={`/reader/${item.series_id}/${item.chapter_id}`}
        className="text-sm font-medium text-fg transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        {item.series_title}
        <span className="text-muted"> — {item.chapter_title}</span>
      </Link>
      <p className="mt-1.5 text-sm leading-relaxed text-muted">
        {segments.map((segment, index) =>
          segment.highlight ? (
            <mark key={index} className="rounded bg-primary/20 px-0.5 text-fg">
              {segment.text}
            </mark>
          ) : (
            <span key={index}>{segment.text}</span>
          ),
        )}
      </p>
      <p className="mt-2 text-xs text-muted/80">
        {item.word_count.toLocaleString()} words · {item.engine}
      </p>
    </li>
  );
}

function QueueStatus() {
  const metrics = useOcrMetrics();
  const jobs = useOcrJobs();

  const tiles = metrics.data
    ? [
        { label: "Completed", value: metrics.data.jobs.completed },
        { label: "Failed", value: metrics.data.jobs.failed },
        { label: "Pages processed", value: metrics.data.pages.processed },
        { label: "Pages/sec", value: metrics.data.performance.pages_per_sec },
      ]
    : [];

  return (
    <section className="space-y-4" aria-labelledby="ocr-queue-heading">
      <h2 id="ocr-queue-heading" className="text-sm font-medium text-muted">
        OCR queue
      </h2>

      {metrics.isError ? (
        <p className="text-sm text-danger">{errorMessage(metrics.error)}</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {tiles.map((tile) => (
            <div key={tile.label} className="glass-card rounded-xl p-4">
              <div className="text-2xl font-semibold tabular-nums text-fg">{tile.value}</div>
              <div className="mt-1 text-xs text-muted">{tile.label}</div>
            </div>
          ))}
        </div>
      )}

      {jobs.isError ? (
        <p className="text-sm text-danger">{errorMessage(jobs.error)}</p>
      ) : jobs.data && jobs.data.length === 0 ? (
        <p className="text-sm text-muted">The OCR queue is empty.</p>
      ) : (
        <ul className="space-y-2">
          {jobs.data?.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </ul>
      )}
    </section>
  );
}

function JobRow({ job }: { job: OcrJob }) {
  const retry = useRetryOcrJob();
  const cancel = useCancelOcrJob();
  const isActive = job.status === "queued" || job.status === "processing";
  const isRetryable = job.status === "failed" || job.status === "cancelled";
  const busy = retry.isPending || cancel.isPending;

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-border/50 bg-surface-2 px-4 py-3">
      <span
        className={cn(
          "inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize",
          jobStatusClasses(job.status),
        )}
      >
        {job.status}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm text-fg">Chapter #{job.chapter_id}</div>
        <div className="text-xs text-muted">
          {job.pages_done}/{job.pages_total || "?"} pages · {job.engine}
          {job.retry_count > 0 ? ` · ${job.retry_count} retries` : ""}
        </div>
        {job.error ? (
          <div className="mt-1 truncate text-xs text-danger" title={job.error}>
            {job.error}
          </div>
        ) : null}
      </div>
      {isRetryable ? (
        <Button
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() => retry.mutate(job.id)}
        >
          <RefreshCw className="size-4" aria-hidden />
          Retry
        </Button>
      ) : null}
      {isActive ? (
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() => cancel.mutate(job.id)}
        >
          <X className="size-4" aria-hidden />
          Cancel
        </Button>
      ) : null}
    </li>
  );
}
