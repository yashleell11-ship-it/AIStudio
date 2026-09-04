import { encodePathKey } from "@/services/http";
import type { ChapterId } from "@/types/api";

/**
 * The novel reader route, shaped exactly like the manga one
 * (`features/reader/reader-link.ts`): path segments, every one
 * `encodeURIComponent`-encoded, with the chapter key as a `[...chapterKey]`
 * catch-all so opaque keys containing `/` survive.
 *
 * A separate route rather than a `?kind=novel` on `/reader/…` because the two
 * readers share no rendering at all — one is a virtualized image strip, the
 * other is a text column — and because the app shell keys its immersive
 * treatment off the path.
 *
 * `page` is the progress BUCKET (see `progress.ts`), carried in the same
 * `?page=` the manga reader uses so the series page's "Continue" link needs no
 * novel-specific branch.
 */
export function novelChapterHref(ref: ChapterId, page?: number): string {
  const base = `/novels/${encodeURIComponent(ref.sourceId)}/${encodeURIComponent(
    ref.seriesKey,
  )}/${encodePathKey(ref.chapterKey)}`;
  return page && page > 1 ? `${base}?page=${page}` : base;
}
