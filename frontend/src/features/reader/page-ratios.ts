import { readScopedString, writeScopedString } from "@/lib/scoped-storage";

/**
 * A chapter's measured page shapes, per (user, profile).
 *
 * Nine connectors report `width`/`height` in the manifest and the reader
 * reserves those pages' exact extent from the first frame. The rest report
 * nothing, so the first paint of every one of their chapters stands on a
 * population prior (`UNKNOWN_PAGE_ASPECT`) that is right on average and wrong
 * on any individual webtoon strip. But the browser learns each page's true
 * shape the instant it decodes — `naturalWidth`/`naturalHeight` — and a reader
 * re-opens chapters constantly: reading on, coming back the next day, resuming
 * after a window resize. Writing that down turns the SECOND open of a chapter
 * into the same first-frame-exact case the reporting connectors already get.
 *
 * An ASPECT RATIO, not a height. A height is only true for the column width and
 * zoom it was measured at, so it is a lie the moment the window is resized;
 * `height / width` is the page itself and survives both. It is also exactly the
 * shape of the thing the manifest would have carried, which is why the strip
 * can feed it into the same estimate path rather than a parallel one.
 *
 * Scoped like every other reader store: what you have read is per profile, and
 * a device-global key here would say which chapters a persona had opened.
 * Best-effort throughout — a miss costs one chapter's first frame, nothing more
 * — so every failure path returns "nothing remembered" rather than throwing.
 */
const RATIO_PREFIX = "manhwamaniacs-reader-page-ratios:";

/**
 * Pages remembered per chapter.
 *
 * Chapters run to a few dozen pages; the cap only stops a pathological listing
 * (some novel sources report thousands) from turning one key into a blob big
 * enough to threaten the whole profile's storage quota.
 */
const MAX_REMEMBERED_PAGES = 400;

/** Ratios outside this are not a page shape, they are a decode that went wrong. */
const MIN_RATIO = 0.05;
const MAX_RATIO = 100;

function storageKey(chapterKey: string): string {
  return `${RATIO_PREFIX}${chapterKey}`;
}

/**
 * Two decimals: at the tallest strip measured (h/w 23) that is a 0.5% error on
 * a 15,000 px row — well under a scroll frame — for about a third of the bytes
 * a full float costs.
 */
function encodeRatio(ratio: number | null): string {
  if (ratio == null || !(ratio >= MIN_RATIO) || !(ratio <= MAX_RATIO)) return "";
  return ratio.toFixed(2);
}

function decodeRatio(raw: string): number | null {
  if (raw === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < MIN_RATIO || value > MAX_RATIO) return null;
  return value;
}

/**
 * Remembered shapes for a chapter, indexed by page number - 1. `null` at an
 * index means that page was never measured; an empty array means the chapter is
 * unknown.
 */
export function readPageRatios(chapterKey: string): (number | null)[] {
  const raw = readScopedString(storageKey(chapterKey));
  if (raw == null || raw === "") return [];
  return raw.split(",", MAX_REMEMBERED_PAGES).map(decodeRatio);
}

/** Write a chapter's shapes. Trailing unknowns are dropped, not stored. */
export function writePageRatios(
  chapterKey: string,
  ratios: ReadonlyArray<number | null>,
): void {
  // `Array.from`, not `map`: a page measured out of order leaves HOLES in the
  // array, and `map` skips holes instead of encoding them as unknown.
  const encoded = Array.from(
    { length: Math.min(ratios.length, MAX_REMEMBERED_PAGES) },
    (_, index) => encodeRatio(ratios[index] ?? null),
  );
  while (encoded.length > 0 && encoded[encoded.length - 1] === "") {
    encoded.pop();
  }
  if (encoded.length === 0) return;
  writeScopedString(storageKey(chapterKey), encoded.join(","));
}

/**
 * The aspect ratio of a decoded image, or null when the browser has not
 * resolved one. A page that failed to decode reports 0x0, and a ratio derived
 * from it would be remembered forever as this chapter's truth.
 */
export function naturalPageRatio(width: number, height: number): number | null {
  if (!(width > 0) || !(height > 0)) return null;
  const ratio = height / width;
  return ratio >= MIN_RATIO && ratio <= MAX_RATIO ? ratio : null;
}
