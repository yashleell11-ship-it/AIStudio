import type { StorageScope } from "@/lib/scoped-storage";
import { novelChapterHref } from "@/features/novels/novel-link";
import type { ChapterId } from "@/types/api";
import type { SaveChapterRequest } from "./protocol";
import { absoluteUrl, chapterCacheKey } from "./save-request";

/**
 * Turning a novel chapter into a download plan.
 *
 * A prose chapter is ONE GET — `/novels/chapter?source=&series=&chapter=`
 * returns the whole thing as sanitized paragraphs — so it needs no new worker
 * message and no new cache: it is a `SaveChapterRequest` with no images, whose
 * `payloadUrl` is that endpoint. `sw-policy.js` already classifies it
 * `network-then-saved`, which is the right rule for text as well as for a
 * manifest: the live copy wins whenever there is one, and the stored copy is
 * what answers when the fetch fails. `pageIdsOf` finds no `pages` array in it,
 * so a novel chapter is never wrongly marked stale.
 *
 * That is what makes the owner's "download whole series for novels too"
 * affordable on the web: a 400-chapter book is a few megabytes of text, where
 * the same count of manga chapters is gigabytes of page images.
 *
 * The URL has to be byte-identical to the one `novelsApi.chapter` asks for,
 * because Cache Storage matches on the exact string. `services/http.ts` builds
 * it with `URLSearchParams` in `source, series, chapter` order via
 * `sourceChapterQuery`, and so does this.
 */

export interface NovelSaveRequestInput {
  ref: ChapterId;
  /** For the `/downloads` screen, which lists chapters under their series. */
  title: string;
  seriesTitle: string | null;
  scope: StorageScope;
  /** Absolute API base, e.g. `https://host/api`, without a trailing slash. */
  apiBase: string;
  origin: string;
  /** The chapter body, when the page already holds it. */
  payloadJson: string | null;
}

export function novelChapterUrl(base: string, ref: ChapterId): string {
  const params = new URLSearchParams({
    source: ref.sourceId,
    series: ref.seriesKey,
    chapter: ref.chapterKey,
  });
  return `${base.replace(/\/+$/, "")}/novels/chapter?${params.toString()}`;
}

export function buildNovelSaveRequest({
  ref,
  title,
  seriesTitle,
  scope,
  apiBase,
  origin,
  payloadJson,
}: NovelSaveRequestInput): SaveChapterRequest {
  const payloadUrl = novelChapterUrl(apiBase, ref);
  return {
    key: chapterCacheKey(ref),
    sourceId: ref.sourceId,
    seriesKey: ref.seriesKey,
    chapterKey: ref.chapterKey,
    title,
    seriesTitle,
    medium: "novel",
    scope,
    profileId: scope.profileId,
    documentUrl: absoluteUrl(novelChapterHref(ref), origin),
    payloadUrl,
    payloadJson,
    // No page images: the text IS the chapter. `runSave` reads "every page
    // saved" off this list, so an empty one settles as `ready` the moment the
    // payload is stored, which is the truth for prose.
    imageUrls: [],
    extraUrls: [payloadUrl],
  };
}
