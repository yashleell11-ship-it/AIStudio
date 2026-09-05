/**
 * The client half of the reader page proxy's `?w=` contract.
 *
 * The backend renders a page at a requested width and SNAPS it onto its own
 * closed ladder (`backend/services/image_resize.py`), reporting what it served
 * in `X-Page-Width`. That ladder is deliberately NOT mirrored here — same rule,
 * same reason, as the cover proxy's client half in `lib/cover-url.ts`: a second
 * copy of it drifts the first time a rung moves, and the whole point of the
 * server snapping is that a client may ask for any width at all. All that is
 * decided here is how many DEVICE pixels the box a page is painted into holds.
 *
 * ### What this is actually worth — measured, and narrower than it sounds
 *
 * On a phone at DPR 3 it is close to inert. Webtoon sources publish strips
 * 720-800 px wide, which is at or below what a 390 px column at DPR 3 already
 * asks for, and the server never upscales: 1 of 24 sampled pages was
 * downscaled. On DESKTOP at DPR 1 the reader column is 768 CSS px and 10 of the
 * same 24 pages get downscaled, one from 729 KB to 130 KB. So this is a desktop
 * win, and it is not, and was never, the fix for reader jank.
 *
 * ### Sharpness outranks bytes
 *
 * The owner reads manga, so a page is never asked for below the size it will be
 * painted at. Two rules follow:
 *
 *  - The width baked into a page URL is the DEFAULT box — the reader column at
 *    zoom 1, which is what the continuous strip paints into and, not
 *    incidentally, what an offline save stores the page under.
 *  - A view that paints WIDER than that (zoomed past 1, or a paged fit that
 *    resolves larger than the column) drops the parameter and takes the
 *    original, which is the sharpest thing that exists. It is dropped rather
 *    than raised on purpose: raising it would mint a new URL per zoom notch,
 *    re-fetching every page ten times on the way from 1.0x to 2.0x, on a box
 *    that caches nothing and re-renders every request.
 *
 * `next/image` cannot do any of this itself — its optimizer fetches without
 * cookies and the page route requires `mm_session`, so pages render
 * `unoptimized` with no `srcset`. WebP needs nothing from us either: the server
 * only honours a literal `image/webp` in `Accept`, and that is exactly what
 * browsers send for `<img>` and `new Image()` requests, which is every request
 * the reader makes for page bytes.
 */

import { imagePixelRatio } from "@/lib/device-pixels";
import { MAX_CONTENT_WIDTH } from "./page-layout";

/**
 * The route declares `w` as 1..10000 and answers anything outside it with a
 * 422 — a broken page rather than a heavy one. This is that range, NOT the snap
 * ladder: past the top rung the server serves the original anyway, so clamping
 * here only keeps an absurd hint on a huge panel from failing outright.
 */
const MAX_REQUEST_WIDTH = 10000;

/**
 * The viewport assumed off the main thread. The reader is client-rendered —
 * the manifest arrives through react-query in the browser — so this only keeps
 * the builder a pure function under Node and vitest.
 */
const SSR_VIEWPORT_WIDTH = 1280;

/**
 * The page-bytes route: `/sources/{source}/pages/{page:path}/image`. Same shape
 * the service worker matches on (`public/sw-policy.js`). A manifest URL is not
 * always ours — several connectors hand back absolute CDN URLs — and a `?w=` on
 * a third party's URL is useless at best and breaks a signed link at worst.
 */
const PAGE_PROXY_PATTERN = /\/sources\/[^/]+\/pages\/.+\/image$/;

function viewportWidth(): number {
  if (typeof window === "undefined") {
    return SSR_VIEWPORT_WIDTH;
  }
  const width = window.innerWidth;
  return Number.isFinite(width) && width > 0 ? width : SSR_VIEWPORT_WIDTH;
}

/**
 * The reader column in CSS pixels at zoom 1 — the strip's `max-w-3xl`, or the
 * viewport when that is narrower. Read here rather than measured from the
 * scroll element because the URL is built when the manifest lands, before any
 * of it is mounted; a width settled in an effect afterwards would rewrite every
 * page URL and fetch the whole chapter twice.
 */
export function readerColumnWidth(): number {
  return Math.min(viewportWidth(), MAX_CONTENT_WIDTH);
}

/** Device pixels to ask for, for a box `cssWidth` CSS pixels wide. */
export function pageRequestWidth(cssWidth: number): number | null {
  if (!(cssWidth > 0)) return null;
  const width = Math.round(cssWidth * imagePixelRatio());
  return Math.min(Math.max(width, 1), MAX_REQUEST_WIDTH);
}

export function isPageProxyUrl(url: string): boolean {
  return PAGE_PROXY_PATTERN.test(url.split(/[?#]/, 1)[0]);
}

/** The `w` a page URL already carries, or null when it carries none. */
export function pageUrlWidth(url: string): number | null {
  const query = url.split("#", 1)[0].split("?")[1];
  if (!query) return null;
  const value = new URLSearchParams(query).get("w");
  if (value === null) return null;
  const width = Number(value);
  return Number.isFinite(width) && width > 0 ? width : null;
}

/**
 * Add the width a `cssWidth`-wide box implies to a page proxy URL.
 *
 * Every fallback — not our URL, no usable width — lands on "serve the
 * original", which is what the reader did before this existed.
 */
export function withPageWidth(url: string, cssWidth: number): string {
  if (!isPageProxyUrl(url)) return url;
  const width = pageRequestWidth(cssWidth);
  if (width === null) return url;
  return `${url}${url.includes("?") ? "&" : "?"}w=${width}`;
}

/** Drop a `w` the URL carries, leaving any other query intact. */
function withoutPageWidth(url: string): string {
  const [head, hash = ""] = splitHash(url);
  const [path, query] = splitQuery(head);
  if (query === undefined) return url;
  const params = new URLSearchParams(query);
  params.delete("w");
  const rest = params.toString();
  return `${path}${rest ? `?${rest}` : ""}${hash ? `#${hash}` : ""}`;
}

function splitHash(url: string): [string, string?] {
  const at = url.indexOf("#");
  return at === -1 ? [url] : [url.slice(0, at), url.slice(at + 1)];
}

function splitQuery(url: string): [string, string?] {
  const at = url.indexOf("?");
  return at === -1 ? [url] : [url.slice(0, at), url.slice(at + 1)];
}

/**
 * The URL to paint into a box `cssWidth` CSS pixels wide.
 *
 * Returns the URL UNTOUCHED whenever the baked width already covers the box —
 * which is the common case, and has to stay byte-identical: it is the string
 * the strip's prefetch warmed, the `<img>` the browser already holds, the key
 * an offline save stored the page under, and a `memo` boundary that only bails
 * on referential equality. Only a box that would be painted larger than the
 * page was requested at changes anything, and then only by dropping to the
 * original.
 */
export function pageImageUrlForBox(url: string, cssWidth: number): string {
  const baked = pageUrlWidth(url);
  if (baked === null) return url;
  const wanted = pageRequestWidth(cssWidth);
  if (wanted === null || wanted <= baked) return url;
  return withoutPageWidth(url);
}
