"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, ScanText, Search, TriangleAlert, WifiOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/ui/empty-state";
import { HeroHeading } from "@/components/premium/HeroHeading";
import { useFollowedIndex } from "@/features/library/hooks";
import { apiErrorMessage, resolveViewState } from "@/lib/view-state";
import { useOcrSearch } from "../hooks";
import { ocrResultHref } from "../result-link";
import { parseSnippet } from "../snippet";
import type { OcrSearchResultItem } from "../types";

const SEARCH_DEBOUNCE_MS = 300;

export function OcrSearchView() {
  return (
    <div className="page-shell">
      <div className="page-container space-y-8">
        <header>
          <HeroHeading className="leading-none md:text-6xl">
            OCR Search
          </HeroHeading>
          <p className="mt-2 text-sm text-muted">
            Search extracted dialogue across the series you follow, and jump
            straight to the chapter it appears in.
          </p>
        </header>

        <DialogueSearch />
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

  const ocrQuery = useOcrSearch(query);
  const { data, isFetching, error } = ocrQuery;
  const { titles } = useFollowedIndex();
  const trimmed = query.trim();
  const results = data?.items ?? [];
  const viewState = resolveViewState({
    // `isLoading` (not `isFetching`) so a debounce-triggered refetch of an
    // already-answered query keeps showing the previous results instead of
    // flashing back to the "type to search" state.
    isLoading: trimmed.length > 0 && ocrQuery.isLoading,
    error: trimmed.length > 0 ? error : null,
    isEmpty: results.length === 0,
  });

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

      {!trimmed ? (
        <EmptyState
          icon={ScanText}
          title="Search the dialogue you remember"
          description="Type at least one word to search text extracted from chapters you follow, and jump straight to where it appears."
        />
      ) : viewState === "loading" ? (
        <ul className="space-y-2" aria-busy="true">
          {Array.from({ length: 3 }).map((_, index) => (
            <li key={index} className="h-20 animate-pulse rounded-xl bg-surface-2" />
          ))}
        </ul>
      ) : viewState === "offline" ? (
        <EmptyState
          tone="offline"
          icon={WifiOff}
          title="You're offline"
          description="Dialogue search needs a connection to run. Chapters you've downloaded still open with no connection at all."
          action={{ label: "Go to Downloads", href: "/downloads" }}
        />
      ) : viewState === "error" ? (
        <EmptyState
          tone="error"
          icon={TriangleAlert}
          title="Search failed"
          description={apiErrorMessage(error, "Something went wrong.")}
          action={{ label: "Try again", onClick: () => void ocrQuery.refetch() }}
        />
      ) : viewState === "empty" ? (
        <EmptyState
          icon={ScanText}
          title="No dialogue matches"
          description={`Nothing found for "${trimmed}" in the chapters you follow.`}
        />
      ) : (
        <ul className="space-y-2">
          {results.map((item) => (
            <SearchResult
              key={`${item.source_id}:${item.series_key}:${item.chapter_key}`}
              item={item}
              seriesTitle={titles.get(`${item.source_id}:${item.series_key}`)}
            />
          ))}
        </ul>
      )}

      {data && data.has_more ? (
        <p className="text-xs text-muted">
          Showing the first {results.length} of {data.total} matches. Refine your
          query to narrow results.
        </p>
      ) : null}
    </section>
  );
}

function SearchResult({
  item,
  seriesTitle,
}: {
  item: OcrSearchResultItem;
  seriesTitle?: string;
}) {
  const segments = parseSnippet(item.snippet);
  return (
    <li className="rounded-xl border border-border/50 bg-surface-2 p-4">
      <Link
        href={ocrResultHref(item)}
        className="text-sm font-medium text-fg transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
      >
        {seriesTitle ?? item.series_key}
        <span className="text-muted"> — {item.chapter_key}</span>
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
