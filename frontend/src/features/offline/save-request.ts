import type { StorageScope } from "@/lib/scoped-storage";
import type { ReaderChapterContent } from "@/features/reader/types";
import { readerChapterHref } from "@/features/reader/reader-link";
import type { SaveChapterRequest } from "./protocol";

/**
 * Turning an open chapter into a download plan.
 *
 * Pure on purpose: the URLs it produces have to be byte-identical to the ones
 * the app will later ask for, because Cache Storage matches on the exact URL.
 *
 * Source-native (spec §3.2):
 *   payload  {apiBase}/reader/chapter/manifest?source=&series=&chapter=
 *   pages    absolute source-proxy URLs straight from the manifest
 *
 * The service worker matcher was repointed at these shapes in the 1b slice:
 * `sw-policy.js` carries the source-proxy page-bytes route and the c1 -> c2
 * cache migration for chapters that were keyed the old way.
 */

/** Unique per chapter. The cache it lives in is already per (user, profile). */
export function chapterCacheKey(
  ref: { sourceId: string; seriesKey: string; chapterKey: string } | string,
): string {
  if (typeof ref === "string") return `chapter:${ref}`;
  return `chapter:${ref.sourceId}:${ref.seriesKey}:${ref.chapterKey}`;
}

export function absoluteUrl(url: string, origin: string): string {
  try {
    return new URL(url, origin).toString();
  } catch {
    return url;
  }
}

export interface SaveRequestInput {
  chapter: ReaderChapterContent;
  scope: StorageScope;
  /** Absolute API base, e.g. `https://host/api`, without a trailing slash. */
  apiBase: string;
  origin: string;
  /** The raw manifest body, when the page already holds it. */
  payloadJson: string | null;
}

/**
 * A chapter is savable once its page list has resolved. (Every chapter is now a
 * source chapter; the SW is the only Cache Storage writer.)
 */
export function isSavableChapter(chapter: ReaderChapterContent): boolean {
  return chapter.pages.length > 0;
}

function manifestUrl(base: string, chapter: ReaderChapterContent): string {
  const params = new URLSearchParams({
    source: chapter.sourceId,
    series: chapter.seriesKey,
    chapter: chapter.chapterKey,
  });
  return `${base}/reader/chapter/manifest?${params.toString()}`;
}

export function buildSaveRequest({
  chapter,
  scope,
  apiBase,
  origin,
  payloadJson,
}: SaveRequestInput): SaveChapterRequest {
  const base = apiBase.replace(/\/+$/, "");
  const payloadUrl = manifestUrl(base, chapter);

  return {
    key: chapterCacheKey(chapter),
    sourceId: chapter.sourceId,
    seriesKey: chapter.seriesKey,
    chapterKey: chapter.chapterKey,
    title: chapter.title,
    seriesTitle: chapter.seriesTitle ?? null,
    scope,
    profileId: scope.profileId,
    documentUrl: absoluteUrl(
      readerChapterHref({
        sourceId: chapter.sourceId,
        seriesKey: chapter.seriesKey,
        chapterKey: chapter.chapterKey,
      }),
      origin,
    ),
    payloadUrl,
    payloadJson,
    imageUrls: chapter.pages.map((page) => absoluteUrl(page.imageUrl, origin)),
    extraUrls: [payloadUrl],
  };
}
