import { describe, expect, it } from "vitest";
import { sourceChapterQuery } from "@/services/http";
import type { StorageScope } from "@/lib/scoped-storage";
import { buildNovelSaveRequest, novelChapterUrl } from "./novel-save-request";

/**
 * A saved novel chapter is answered from Cache Storage, which matches on the
 * exact URL string. The URL built here therefore has to be byte-identical to
 * the one `novelsApi.chapter` asks for — a chapter stored under a URL nobody
 * requests is bytes on the device that never open.
 */

const SCOPE: StorageScope = { userId: 3, profileId: 7 };
const API_BASE = "https://host.example/api";
const ORIGIN = "https://host.example";
const REF = { sourceId: "novelbin", seriesKey: "book/lotm", chapterKey: "ch/12" };

/**
 * `buildUrl` from `services/http.ts`, which is not exported. Kept in step by
 * the exact-string assertion below: both would have to be wrong the same way.
 */
function httpUrl(path: string, query: Record<string, string>): string {
  const url = new URL(path.replace(/^\//, ""), `${API_BASE}/`);
  for (const [key, value] of Object.entries(query)) url.searchParams.set(key, value);
  return url.toString();
}

describe("novelChapterUrl", () => {
  it("is what the app's own chapter request builds", () => {
    expect(novelChapterUrl(API_BASE, REF)).toBe(
      httpUrl("/novels/chapter", sourceChapterQuery(REF)),
    );
  });

  it("percent-encodes the opaque keys, in the order the client sends them", () => {
    expect(novelChapterUrl(API_BASE, REF)).toBe(
      "https://host.example/api/novels/chapter" +
        "?source=novelbin&series=book%2Flotm&chapter=ch%2F12",
    );
  });

  it("tolerates a trailing slash on the base", () => {
    expect(novelChapterUrl(`${API_BASE}/`, REF)).toBe(novelChapterUrl(API_BASE, REF));
  });
});

describe("buildNovelSaveRequest", () => {
  const request = buildNovelSaveRequest({
    ref: REF,
    title: "Chapter 12",
    seriesTitle: "Lord of the Mysteries",
    scope: SCOPE,
    apiBase: API_BASE,
    origin: ORIGIN,
    payloadJson: '{"paragraphs":["a"]}',
  });

  it("shares the manga cache key shape, so one index holds both", () => {
    expect(request.key).toBe("chapter:novelbin:book/lotm:ch/12");
  });

  it("stores no images — the text is the chapter", () => {
    expect(request.imageUrls).toEqual([]);
    expect(request.extraUrls).toEqual([request.payloadUrl]);
  });

  it("hands the worker the body the page already holds", () => {
    expect(request.payloadJson).toBe('{"paragraphs":["a"]}');
  });

  it("points the document URL at the novel reader route", () => {
    expect(request.documentUrl).toBe(
      "https://host.example/novels/novelbin/book%2Flotm/ch/12",
    );
  });

  it("carries the scope's profile, like every other save", () => {
    expect(request).toMatchObject({ scope: SCOPE, profileId: 7 });
  });
});
