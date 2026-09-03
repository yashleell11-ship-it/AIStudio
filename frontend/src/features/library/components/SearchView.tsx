"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronUp,
  Clock,
  Search,
  SlidersHorizontal,
  TrendingUp,
} from "lucide-react";
import { ApiError } from "@/types/api";
import { Input } from "@/components/ui/input";
import { useShortcut } from "@/lib/keyboard";
import { cn } from "@/lib/cn";
import { useFederatedSearch, useRetrySearchSource } from "@/features/sources/hooks";
import {
  globalSearchScopeLabel,
  searchGroupKey,
  searchResultCount,
  splitSearchGroups,
} from "@/features/sources/global-search";
import {
  getRecentSearchesServerSnapshot,
  getRecentSearchesSnapshot,
  subscribeRecentSearches,
  writeRecentSearch,
} from "@/features/library/recent-searches";
import { GlobalSearchGroupSection } from "./GlobalSearchGroupSection";
import { SearchResultCardSkeleton } from "./GlobalSearchResultCard";

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
      className="rounded-full border border-border/50 bg-white/[0.03] px-3 py-1.5 text-sm text-muted transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
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
      <Icon className="size-3.5 text-primary" aria-hidden />
      <span className="text-[11px] font-semibold uppercase tracking-widest text-muted">
        {label}
      </span>
    </div>
  );
}

export function SearchView() {
  const [query, setQuery] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [quietOpen, setQuietOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const lastPersistedRef = useRef<string | null>(null);
  const trimmedQuery = query.trim();
  const searchParams = useMemo(
    () => ({ q: trimmedQuery, page: 1, per_page: 40 }),
    [trimmedQuery],
  );
  const searchQuery = useFederatedSearch(searchParams);
  const retrySource = useRetrySearchSource(searchParams);
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
  // The flat `items` list is the backend's legacy view; sections are rendered
  // from `groups` so a source that failed or returned nothing says so itself.
  const groups = useMemo(() => searchQuery.data?.groups ?? [], [searchQuery.data]);
  const { visible, quiet } = useMemo(() => splitSearchGroups(groups), [groups]);
  const resultCount = searchResultCount(groups);
  const scopeLabel = searchQuery.data
    ? globalSearchScopeLabel(
        searchQuery.data.sources_queried,
        searchQuery.data.sources_failed,
      )
    : null;

  const renderGroup = (group: (typeof groups)[number]) => {
    // Null for the local library group — there is no remote call to retry.
    const sourceId = group.source;
    return (
      <GlobalSearchGroupSection
        key={searchGroupKey(group)}
        group={group}
        isRetrying={retrySource.isPending && retrySource.variables === sourceId}
        onRetry={sourceId ? () => retrySource.mutate(sourceId) : undefined}
      />
    );
  };

  return (
    <div className="min-h-full bg-bg px-6 py-8 md:px-10">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8 text-center">
          <h1 className="font-display text-4xl uppercase tracking-wide text-fg md:text-5xl">
            Search
          </h1>
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
            className="h-14 rounded-2xl border-border/50 bg-white/[0.03] pl-14 text-base focus-visible:ring-primary/40"
            aria-label="Search library and sources"
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
                  "inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/[0.03] px-4 py-2 text-sm text-muted transition-colors hover:border-primary/30 hover:text-fg",
                  filtersOpen && "border-primary/30 bg-primary/10 text-primary",
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
                  Search spans your local library and every enabled source
                  connector at once.
                </p>
                <p className="mt-2">
                  Press{" "}
                  <kbd className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-xs">/</kbd> to
                  focus search. Use the Library page for status, sort, and collection filters.
                </p>
              </div>
            ) : null}

            <div className="glass-panel rounded-3xl border border-dashed border-border/50 p-10 text-center">
              <Search className="mx-auto mb-3 size-8 text-muted/40" aria-hidden />
              <p className="text-lg font-medium text-fg">Start typing to search</p>
              <p className="mt-2 text-sm text-muted">
                Search your library and every source connector at once.
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
            <div className="mb-4">
              <p className="text-sm text-muted">
                {searchQuery.isLoading
                  ? "Searching sources…"
                  : `${resultCount.toLocaleString()} ${resultCount === 1 ? "result" : "results"} found`}
              </p>
              {!searchQuery.isLoading && scopeLabel ? (
                <p className="mt-0.5 text-xs text-muted/70">{scopeLabel}</p>
              ) : null}
            </div>

            {searchQuery.isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, index) => (
                  <SearchResultCardSkeleton key={index} />
                ))}
              </div>
            ) : visible.length === 0 && quiet.length === 0 ? (
              <div className="glass-panel rounded-3xl border border-dashed border-border/50 p-10 text-center">
                <p className="text-lg font-medium text-fg">No results found</p>
                <p className="mt-2 text-sm text-muted">
                  Try a different search term across your library and sources.
                </p>
              </div>
            ) : (
              <>
                {visible.map(renderGroup)}

                {quiet.length > 0 ? (
                  <div className="mt-2">
                    <button
                      type="button"
                      onClick={() => setQuietOpen((open) => !open)}
                      aria-expanded={quietOpen}
                      className="inline-flex items-center gap-2 rounded-full border border-border/50 bg-white/[0.03] px-4 py-2 text-sm text-muted transition-colors hover:border-primary/30 hover:text-fg"
                    >
                      {quietOpen ? (
                        <ChevronUp className="size-4" aria-hidden />
                      ) : (
                        <ChevronDown className="size-4" aria-hidden />
                      )}
                      {quietOpen ? "Hide" : "Show"} {quiet.length}{" "}
                      {quiet.length === 1 ? "source" : "sources"} with no matches
                    </button>
                    {quietOpen ? (
                      <div className="mt-4">{quiet.map(renderGroup)}</div>
                    ) : null}
                  </div>
                ) : null}
              </>
            )}
          </section>
        ) : null}
      </div>
    </div>
  );
}
