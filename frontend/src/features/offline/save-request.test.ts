import { describe, expect, it } from "vitest";
import type { ReaderChapterContent } from "@/features/reader/types";
import { buildSaveRequest, chapterCacheKey, isSavableChapter } from "./save-request";

/**
 * The download plan has to name URLs the app will later ask for EXACTLY. Cache
 * Storage matches on the whole URL, so a saved chapter whose keys are one
 * character off is a chapter that looks saved and fails to open on a train.
 *
 * The shapes asserted here are the ones `services/http.ts` builds and
 * `features/reader/api.ts` hands the reader.
 */

const ORIGIN = "https://manhwa.example";
const API = `${ORIGIN}/api`;
const SCOPE = { userId: 1, profileId: 10 };

function chapter(overrides: Partial<ReaderChapterContent> = {}): ReaderChapterContent {
  return {
    id: "412",
    seriesId: "7",
    title: "Chapter 12",
    seriesTitle: "Solo Levelling",
    pageCount: 2,
    mode: "local",
    sourceId: null,
    previousChapterId: null,
    nextChapterId: null,
    pages: [
      { id: "1", number: 1, imageUrl: "/api/reader/page/1/image", width: null, height: null },
      { id: "2", number: 2, imageUrl: "/api/reader/page/2/image", width: null, height: null },
    ],
    ...overrides,
  };
}

describe("chapterCacheKey", () => {
  it("is stable and unique per chapter", () => {
    expect(chapterCacheKey("412")).toBe("chapter:412");
    expect(chapterCacheKey(412)).toBe(chapterCacheKey("412"));
    expect(chapterCacheKey(41)).not.toBe(chapterCacheKey(412));
  });
});

describe("isSavableChapter", () => {
  it("accepts a chapter the library actually holds", () => {
    expect(isSavableChapter(chapter())).toBe(true);
  });

  it("refuses an online-source chapter", () => {
    // Its pages come from the upstream scanlation site with no CORS, so the
    // bytes arrive opaque and a stored opaque response is a cached failure.
    expect(isSavableChapter(chapter({ mode: "remote", sourceId: "asura" }))).toBe(false);
  });

  it("refuses a chapter with no pages", () => {
    expect(isSavableChapter(chapter({ pages: [] }))).toBe(false);
  });
});

describe("buildSaveRequest", () => {
  const request = buildSaveRequest({
    chapter: chapter(),
    scope: SCOPE,
    apiBase: API,
    origin: ORIGIN,
    payloadJson: '{"id":412}',
  });

  it("resolves relative page URLs to the absolute keys the cache uses", () => {
    // In production `env.apiUrl` is the same-origin path `/api`, so the reader
    // renders a relative src. A relative cache key would never match it.
    expect(request.imageUrls).toEqual([
      `${API}/reader/page/1/image`,
      `${API}/reader/page/2/image`,
    ]);
  });

  it("leaves an already absolute page URL alone", () => {
    const absolute = buildSaveRequest({
      chapter: chapter({
        pages: [
          {
            id: "9",
            number: 1,
            imageUrl: "http://127.0.0.1:8000/reader/page/9/image",
            width: null,
            height: null,
          },
        ],
      }),
      scope: SCOPE,
      apiBase: "http://127.0.0.1:8000",
      origin: ORIGIN,
      payloadJson: null,
    });
    expect(absolute.imageUrls).toEqual(["http://127.0.0.1:8000/reader/page/9/image"]);
  });

  it("names the chapter payload endpoint the reader will call", () => {
    expect(request.payloadUrl).toBe(`${API}/reader/chapter/412`);
    expect(request.extraUrls).toContain(`${API}/reader/chapter/412`);
  });

  it("names both adjacency lookups exactly as http.ts builds them", () => {
    expect(request.extraUrls).toContain(
      `${API}/reader/chapter/412/adjacent?direction=previous`,
    );
    expect(request.extraUrls).toContain(`${API}/reader/chapter/412/adjacent?direction=next`);
  });

  it("stores the reader route so a cold offline start has a document", () => {
    expect(request.documentUrl).toBe(`${ORIGIN}/reader/7/412`);
  });

  it("tolerates a trailing slash on the API base", () => {
    const trailing = buildSaveRequest({
      chapter: chapter(),
      scope: SCOPE,
      apiBase: `${API}/`,
      origin: ORIGIN,
      payloadJson: null,
    });
    expect(trailing.payloadUrl).toBe(`${API}/reader/chapter/412`);
  });

  it("carries the scope and profile the worker needs to file it correctly", () => {
    expect(request.scope).toEqual(SCOPE);
    expect(request.profileId).toBe(SCOPE.profileId);
  });
});
