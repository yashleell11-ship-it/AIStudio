"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  BookOpen,
  Clock,
  Search,
  SlidersHorizontal,
  TrendingUp,
} from "lucide-react";
import { ApiError } from "@/types/api";
import { Input } from "@/components/ui/input";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import { useSearch } from "@/features/library/hooks";
import { SearchResultCard, SearchResultCardSkeleton } from "./SearchResultCard";

const RECENT_SEARCHES_KEY = "aistudio:recent-searches";
const MAX_RECENT_SEARCHES = 4;

const TRENDING_SUGGESTIONS = [
  "fantasy",
  "romance",
  "action",
  "manhwa",
  "manga",
  "webtoon",
  "horror",
  "sci-fi",
] as const;

function readRecentSearches(): string[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(RECENT_SEARCHES_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is string => typeof item === "string").slice(0, MAX_RECENT_SEARCHES);
  } catch {
    return [];
  }
}

function writeRecentSearch(term: string) {
  const trimmed = term.trim();
  if (trimmed.length < 2 || typeof window === "undefined") {
    return;
  }
  const existing = readRecentSearches().filter(
    (item) => item.toLowerCase() !== trimmed.toLowerCase(),
  );
  const next = [trimmed, ...existing].slice(0, MAX_RECENT_SEARCHES);
  window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(next));
  window.dispatchEvent(new Event("aistudio:recent-searches"));
}

function subscribeRecentSearches(onStoreChange: () => void) {
  const handler = () => onStoreChange();
  window.addEventListener("aistudio:recent-searches", handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener("aistudio:recent-searches", handler);
    window.removeEventListener("storage", handler);
  };
}

function getRecentSearchesSnapshot() {
  return readRecentSearches();
}

function getRecentSearchesServerSnapshot() {
  return [] as string[];
}

function SuggestionChip({
  label,
  onSelect,
}: {
  label: string;
  onSelect: (value: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(label)}
      className="rounded-full border border-border/50 bg-white/[0.03] px-3 py-1.5 text-sm text-muted transition-colors hover:border-violet-500/30 hover:bg-violet-500/10 hover:text-violet-400"
    >
      {label}
    </button>
  );
}

function SectionLabel({
  icon: Icon,
  label,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <Icon className="size-3.5 text-cyan-400" aria-hidden />
      <span className="text-[11px] font-semibold uppercase tracking-widest text-muted">
        {label}
      </span>
    </div>
  );
}

export function SearchView() {
  const [query, setQuery] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const lastPersistedRef = useRef<string | null>(null);
  const trimmedQuery = query.trim();
  const searchQuery = useSearch({ q: trimmedQuery, page: 1, per_page: 40 });
  const recentSearches = useSyncExternalStore(
    subscribeRecentSearches,
    getRecentSearchesSnapshot,
    getRecentSearchesServerSnapshot,
  );

  useEffect(() => {
    if (
      trimmedQuery.length >= 2 &&
      searchQuery.data &&
      !searchQuery.isLoading &&
      lastPersistedRef.current !== trimmedQuery
    ) {
      lastPersistedRef.current = trimmedQuery;
      writeRecentSearch(trimmedQuery);
    }
  }, [trimmedQuery, searchQuery.data, searchQuery.isLoading]);

  useShortcut({
    id: "search.focus-input",
    keys: "/",
    description: "Focus search",
    group: "Search",
    handler: useCallback(() => {
      searchRef.current?.focus();
    }, []),
  });

  const applySuggestion = useCallback((value: string) => {
    setQuery(value);
    searchRef.current?.focus();
  }, []);

  const errorMessage =
    searchQuery.error instanceof ApiError
      ? searchQuery.error.message
      : searchQuery.error
        ? "Search failed. Please try again."
        : null;

  const hasQuery = trimmedQuery.length > 0;
  const results = searchQuery.data?.items ?? [];
  const resultCount = searchQuery.data?.total ?? 0;

  return (
    <div className="min-h-full bg-bg px-6 py-8 md:px-10">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8 text-center">
          <h1 className="text-4xl font-bold tracking-tight text-fg md:text-5xl">Search</h1>
          <p className="mt-2 text-sm text-muted md:text-base">
            Find your next favorite series
          </p>
        </header>

        <div className="relative mb-6">
          <Search
            className="pointer-events-none absolute left-5 top-1/2 size-5 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            ref={searchRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search manga, manhwa, webtoons..."
            className="h-14 rounded-2xl border-border/50 bg-white/[0.03] pl-14 text-base focus-visible:ring-violet-500/30"
            aria-label="Search library"
            autoComplete="off"
          />
        </div>

        {!hasQuery ? (
          <div className="space-y-6">
            {recentSearches.length > 0 ? (
              <section>
                <SectionLabel icon={Clock} label="Recent" />
                <div className="flex flex-wrap gap-2">
                  {recentSearches.map((term) => (
                    <SuggestionChip key={term} label={term} onSelect={applySuggestion} />
                  ))}
                </div>
              </section>
            ) : null}

            <section>
              <SectionLabel icon={TrendingUp} label="Trending" />
              <div className="flex flex-wrap gap-2">
                {TRENDING_SUGGESTIONS.map((term) => (
                  <SuggestionChip key={term} label={term} onSelect={applySuggestion} />
                ))}
              </div>
            </section>

            <div className="flex justify-center pt-2">
              <button
                type="button"
                onClick={() => setFiltersOpen((open) => !open)}
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/[0.03] px-4 py-2 text-sm text-muted transition-colors hover:border-violet-500/30 hover:text-fg",
                  filtersOpen && "border-violet-500/30 bg-violet-500/10 text-violet-400",
                )}
                aria-expanded={filtersOpen}
              >
                <SlidersHorizontal className="size-4" />
                Advanced Filters
              </button>
            </div>

            {filtersOpen ? (
              <div className="glass-panel rounded-xl p-4 text-sm text-muted">
                <p>
                  Search matches titles, authors, and descriptions in your local library.
                </p>
                <p className="mt-2">
                  Press{" "}
                  <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-xs">/</kbd> to
                  focus search. Use the Library page for status, sort, and collection filters.
                </p>
              </div>
            ) : null}

            <div className="glass-panel rounded-xl border border-dashed border-border/50 p-10 text-center">
              <Search className="mx-auto mb-3 size-8 text-muted/40" aria-hidden />
              <p className="text-lg font-medium text-fg">Start typing to search</p>
              <p className="mt-2 text-sm text-muted">
                Search across titles, authors, and descriptions in your library.
              </p>
            </div>
          </div>
        ) : null}

        {errorMessage ? (
          <div className="mb-6 rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-sm text-danger">
            {errorMessage}
          </div>
        ) : null}

        {hasQuery ? (
          <section>
            <SectionLabel icon={BookOpen} label="Results" />
            <p className="mb-4 text-sm text-muted">
              {searchQuery.isLoading
                ? "Searching…"
                : `${resultCount.toLocaleString()} ${resultCount === 1 ? "result" : "results"} found`}
            </p>

            {searchQuery.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, index) => (
                  <SearchResultCardSkeleton key={index} />
                ))}
              </div>
            ) : results.length === 0 ? (
              <div className="glass-panel rounded-xl border border-dashed border-border/50 p-10 text-center">
                <p className="text-lg font-medium text-fg">No results found</p>
                <p className="mt-2 text-sm text-muted">
                  Try a different search term or clear filters.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {results.map((series) => (
                  <SearchResultCard key={series.id} series={series} />
                ))}
              </div>
            )}
          </section>
        ) : null}
      </div>
    </div>
  );
}
