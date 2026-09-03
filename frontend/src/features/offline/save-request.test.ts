import { describe, expect, it } from "vitest";
import type { ReaderChapterContent } from "@/features/reader/types";
import type { StorageScope } from "@/lib/scoped-storage";
import { buildSaveRequest, chapterCacheKey, isSavableChapter } from "./save-request";

/**
 * `buildSaveRequest` turns an open chapter into a download plan whose URLs must
 * be byte-identical to the ones the app will later ask for — Cache Storage
 * matches on the exact URL. Source-native shapes (spec §3.2).
 */

const SCOPE: StorageScope = { userId: 1, profileId: 10 };
const API_BASE = "https://host.example/api";
const ORIGIN = "https://host.example";

function chapter(overrides: Partial<ReaderChapterContent> = {}): ReaderChapterContent {
  return {
    sourceId: "asura",
    seriesKey: "series/solo-levelling",
    chapterKey: "ch/50",
    chapterNumber: 50,
    title: "Chapter 50",
    pageCount: 2,
    previousChapterKey: "ch/49",
    nextChapterKey: "ch/51",
    seriesTitle: "Solo Levelling",
    pages: [
      {
        id: "ch/50:1",
        number: 1,
        imageUrl: "https://host.example/api/sources/asura/pages/p1/image",
        width: null,
        height: null,
      },
      {
        id: "ch/50:2",
        number: 2,
        imageUrl: "/api/sources/asura/pages/p2/image",
        width: null,
        height: null,
      },
    ],
    ...overrides,
  };
}

describe("chapterCacheKey", () => {
  it("is the source-native identity, prefixed", () => {
    expect(
      chapterCacheKey({ sourceId: "asura", seriesKey: "series/x", chapterKey: "ch/9" }),
    ).toBe("chapter:asura:series/x:ch/9");
  });

  it("derives the same key from a whole chapter", () => {
    expect(chapterCacheKey(chapter())).toBe(
      "chapter:asura:series/solo-levelling:ch/50",
    );
  });
});

describe("isSavableChapter", () => {
  it("is true once the page list has resolved", () => {
    expect(isSavableChapter(chapter())).toBe(true);
    expect(isSavableChapter(chapter({ pages: [] }))).toBe(false);
  });
});

describe("buildSaveRequest", () => {
  const request = buildSaveRequest({
    chapter: chapter(),
    scope: SCOPE,
    apiBase: API_BASE,
    origin: ORIGIN,
    payloadJson: '{"cached":true}',
  });

  it("points the payload URL at the manifest endpoint with the encoded query", () => {
    expect(request.payloadUrl).toBe(
      "https://host.example/api/reader/chapter/manifest" +
        "?source=asura&series=series%2Fsolo-levelling&chapter=ch%2F50",
    );
    expect(request.extraUrls).toEqual([request.payloadUrl]);
  });

  it("carries the source-native identity and the cache key", () => {
    expect(request).toMatchObject({
      key: "chapter:asura:series/solo-levelling:ch/50",
      sourceId: "asura",
      seriesKey: "series/solo-levelling",
      chapterKey: "ch/50",
      profileId: 10,
      seriesTitle: "Solo Levelling",
      payloadJson: '{"cached":true}',
    });
  });

  it("resolves every page image to an absolute URL, in page order", () => {
    expect(request.imageUrls).toEqual([
      "https://host.example/api/sources/asura/pages/p1/image",
      "https://host.example/api/sources/asura/pages/p2/image",
    ]);
  });

  it("points the document URL at the unified reader route", () => {
    expect(request.documentUrl).toBe(
      "https://host.example/reader/asura/series%2Fsolo-levelling/ch/50",
    );
  });
});
