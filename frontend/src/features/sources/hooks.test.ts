import { QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readerManifestQueryKey } from "@/features/reader/hooks";
import {
  applyReaderPageCountToSourceChapters,
  applyRefreshedBrowsePage,
  normalizeBrowseFacets,
  prefetchSourceReaderChapter,
  sourceChaptersQueryKey,
  sourceSeriesInfiniteQueryKey,
} from "./hooks";
import type { PaginatedSourceSeries, SourceChapterSummary } from "./types";

function chapter(overrides: Partial<SourceChapterSummary> = {}): SourceChapterSummary {
  return {
    id: "aishiteru-uso-dakedo.10797/c1",
    source_id: "mangakatana",
    series_id: "aishiteru-uso-dakedo.10797",
    title: "Chapter 1",
    number: 1,
    page_count: 0,
    release_date: null,
    ...overrides,
  };
}

/**
 * Regression test for the MangaKatana page_count bug: the connector only
 * learns a chapter's page_count after its pages are fetched once, but the
 * series-page chapters query was never told about it. It kept rendering its
 * cached (page_count: 0) response until it happened to go stale on its own
 * (up to the global 30s staleTime later).
 *
 * Before this fix: nothing updated the chapters query after a reader chapter
 * fetch, so these assertions fail.
 */
describe("applyReaderPageCountToSourceChapters", () => {
  it("patches the cached chapter's page_count in place via setQueryData -- no refetch", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangakatana";
    const seriesId = "aishiteru-uso-dakedo.10797";
    const chapterId = `${seriesId}/c1`;
    const chaptersKey = sourceChaptersQueryKey(sourceId, seriesId);

    queryClient.setQueryData(chaptersKey, [
      chapter({ id: chapterId, page_count: 0 }),
      chapter({ id: `${seriesId}/c2`, page_count: 0 }),
    ]);

    applyReaderPageCountToSourceChapters(queryClient, sourceId, seriesId, chapterId, 24);

    const data = queryClient.getQueryData<SourceChapterSummary[]>(chaptersKey);
    expect(data?.find((c) => c.id === chapterId)?.page_count).toBe(24);
    // The other chapter in the same series is untouched.
    expect(data?.find((c) => c.id === `${seriesId}/c2`)?.page_count).toBe(0);
    // A direct setQueryData write never marks the query invalidated -- there
    // is no background refetch/network request involved, unlike the
    // invalidateQueries fallback path exercised in the tests below.
    expect(queryClient.getQueryState(chaptersKey)?.isInvalidated).toBe(false);
  });

  it("does not touch the chapters cache for a different series", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangakatana";
    const seriesId = "aishiteru-uso-dakedo.10797";
    const otherSeriesId = "some-other-series";
    const otherKey = sourceChaptersQueryKey(sourceId, otherSeriesId);

    queryClient.setQueryData(otherKey, [
      chapter({ id: `${otherSeriesId}/c1`, series_id: otherSeriesId, page_count: 0 }),
    ]);

    applyReaderPageCountToSourceChapters(
      queryClient,
      sourceId,
      seriesId,
      `${seriesId}/c1`,
      12,
    );

    const otherData = queryClient.getQueryData<SourceChapterSummary[]>(otherKey);
    expect(otherData?.[0]?.page_count).toBe(0);
    expect(queryClient.getQueryState(otherKey)?.isInvalidated).toBe(false);
  });

  it("falls back to invalidating only that series' query when there is no cached list to patch", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangakatana";
    const seriesId = "aishiteru-uso-dakedo.10797";
    const otherSeriesKey = sourceChaptersQueryKey(sourceId, "unrelated-series");
    const targetKey = sourceChaptersQueryKey(sourceId, seriesId);

    queryClient.setQueryData(otherSeriesKey, [
      chapter({ id: "unrelated-series/c1", series_id: "unrelated-series", page_count: 0 }),
    ]);

    // No chapters list has been cached yet for `seriesId` -- setQueryData
    // has nothing to patch, so this must fall back to invalidation, scoped
    // only to this series.
    applyReaderPageCountToSourceChapters(
      queryClient,
      sourceId,
      seriesId,
      `${seriesId}/c1`,
      8,
    );

    expect(queryClient.getQueryState(otherSeriesKey)?.isInvalidated).toBe(false);
    // Nothing was cached under the target key either, so invalidation had
    // no existing query to mark -- confirms no phantom query was created.
    expect(queryClient.getQueryState(targetKey)).toBeUndefined();
  });

  it("falls back to invalidation when the cached list exists but doesn't contain the chapter", () => {
    const queryClient = new QueryClient();
    const sourceId = "mangakatana";
    const seriesId = "aishiteru-uso-dakedo.10797";
    const chaptersKey = sourceChaptersQueryKey(sourceId, seriesId);

    queryClient.setQueryData(chaptersKey, [
      chapter({ id: `${seriesId}/c1`, page_count: 0 }),
    ]);

    applyReaderPageCountToSourceChapters(
      queryClient,
      sourceId,
      seriesId,
      `${seriesId}/c-not-in-cache`,
      5,
    );

    expect(queryClient.getQueryState(chaptersKey)?.isInvalidated).toBe(true);
  });
});

function browsePage(overrides: Partial<PaginatedSourceSeries> = {}): PaginatedSourceSeries {
  return {
    items: [],
    page: 1,
    page_size: 20,
    total: 40,
    total_pages: 2,
    has_more: true,
    ...overrides,
  };
}

describe("normalizeBrowseFacets", () => {
  it("drops the sentinel sort and blank facets so they never key the cache", () => {
    expect(normalizeBrowseFacets({ query: "  ", sort: "default", genre: " " })).toEqual({
      query: undefined,
      sort: undefined,
      genre: undefined,
    });
  });

  it("trims what it keeps", () => {
    expect(normalizeBrowseFacets({ query: " solo ", sort: "latest", genre: " Action " })).toEqual({
      query: "solo",
      sort: "latest",
      genre: "Action",
    });
  });
});

describe("sourceSeriesInfiniteQueryKey", () => {
  it("gives the browse listing and its refresh the SAME key", () => {
    // The browse hook passes the sort already reduced to undefined; the refresh
    // button passes the raw active sort. Both must land on one cache entry, or
    // a refresh writes a listing nobody is reading.
    expect(sourceSeriesInfiniteQueryKey("mangadex", { query: "", sort: undefined })).toEqual(
      sourceSeriesInfiniteQueryKey("mangadex", { query: "", sort: "default" }),
    );
  });

  it("separates facets that ask the source different questions", () => {
    const base = sourceSeriesInfiniteQueryKey("mangadex", { query: "" });
    expect(sourceSeriesInfiniteQueryKey("mangadex", { query: "solo" })).not.toEqual(base);
    expect(sourceSeriesInfiniteQueryKey("mangadex", { query: "", genre: "Action" })).not.toEqual(base);
    expect(sourceSeriesInfiniteQueryKey("webtoons", { query: "" })).not.toEqual(base);
  });
});

describe("applyRefreshedBrowsePage", () => {
  it("collapses a paged-through listing back to the one refetched page", () => {
    const queryClient = new QueryClient();
    const key = sourceSeriesInfiniteQueryKey("mangadex", { query: "" });
    queryClient.setQueryData(key, {
      pages: [browsePage({ page: 1 }), browsePage({ page: 2, has_more: false })],
      pageParams: [1, 2],
    });

    const refreshed = browsePage({ page: 1, total: 41 });
    applyRefreshedBrowsePage(queryClient, key, refreshed);

    const data = queryClient.getQueryData<{
      pages: PaginatedSourceSeries[];
      pageParams: number[];
    }>(key);
    expect(data?.pages).toEqual([refreshed]);
    expect(data?.pageParams).toEqual([1]);
    // A direct write, so no background refetch is queued behind it.
    expect(queryClient.getQueryState(key)?.isInvalidated).toBe(false);
  });
});


describe("prefetchSourceReaderChapter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fills the cache entry the reader actually reads", async () => {
    // The regression: the series page warmed `["sources", …, "reader", …]`,
    // which no component reads — the reader renders from the manifest query.
    // So every hover and every open-the-page prefetch was a live chapter
    // scrape that bought nothing, out of the rate-limited `/sources` bucket.
    const manifest = {
      source_id: "asura",
      series_key: "solo-leveling",
      chapter_key: "chapter/1",
      chapter_number: 1,
      page_count: 0,
      pages: [],
      prev: null,
      next: null,
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify(manifest), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      ),
    );

    const client = new QueryClient();
    prefetchSourceReaderChapter(client, "asura", "solo-leveling", "chapter/1");

    await vi.waitFor(() =>
      expect(
        client.getQueryData(
          readerManifestQueryKey({
            sourceId: "asura",
            seriesKey: "solo-leveling",
            chapterKey: "chapter/1",
          }),
        ),
      ).toEqual(manifest),
    );
  });
});
