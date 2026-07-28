import type { StorageScope } from "@/lib/scoped-storage";
import type { ReaderChapterContent } from "@/features/reader/types";
import type { SaveChapterRequest } from "./protocol";

/**
 * Turning an open chapter into a download plan.
 *
 * Pure on purpose: the URLs it produces have to be byte-identical to the ones
 * the app will later ask for, because Cache Storage matches on the exact URL.
 * That makes this the one place where the reader's URL construction is
 * duplicated, and the one place a test can prove the duplication is faithful.
 *
 * The three shapes it must reproduce (all built by `services/http.ts`'s
 * `buildUrl`, which resolves a path against the API base and then appends
 * query parameters):
 *   payload   {apiBase}/reader/chapter/{id}            — features/reader/api.ts
 *   adjacency {apiBase}/reader/chapter/{id}/adjacent?direction=previous|next
 *   page      {apiBase}/reader/page/{pageId}/image     — readerPageImageUrl
 */

/** Unique per chapter. The cache it lives in is already per (user, profile). */
export function chapterCacheKey(chapterId: string | number): string {
  return `chapter:${chapterId}`;
}

/**
 * Absolute form of a URL the app will request.
 *
 * `env.apiUrl` is the same-origin path `/api` in production, so page image URLs
 * arrive here relative. Cache Storage keys are always absolute, so a relative
 * key would simply never match the request the reader makes.
 */
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
  /** The raw `/reader/chapter/{id}` body, when the page already holds it. */
  payloadJson: string | null;
}

/**
 * Chapters served by an online source are not savable.
 *
 * Their pages are scraped from the upstream scanlation site: cross-origin, no
 * CORS, so the bytes come back opaque and a stored opaque response is a cached
 * failure that can never be told apart from a success. Saving is therefore
 * offered only for chapters the library actually holds.
 */
export function isSavableChapter(chapter: ReaderChapterContent): boolean {
  return chapter.mode === "local" && chapter.pages.length > 0;
}

export function buildSaveRequest({
  chapter,
  scope,
  apiBase,
  origin,
  payloadJson,
}: SaveRequestInput): SaveChapterRequest {
  const base = apiBase.replace(/\/+$/, "");
  const payloadUrl = `${base}/reader/chapter/${chapter.id}`;

  return {
    key: chapterCacheKey(chapter.id),
    chapterId: chapter.id,
    seriesId: chapter.seriesId,
    title: chapter.title,
    seriesTitle: chapter.seriesTitle ?? null,
    scope,
    profileId: scope.profileId,
    documentUrl: absoluteUrl(`/reader/${chapter.seriesId}/${chapter.id}`, origin),
    payloadUrl,
    payloadJson,
    imageUrls: chapter.pages.map((page) => absoluteUrl(page.imageUrl, origin)),
    extraUrls: [
      payloadUrl,
      `${base}/reader/chapter/${chapter.id}/adjacent?direction=previous`,
      `${base}/reader/chapter/${chapter.id}/adjacent?direction=next`,
    ],
  };
}
