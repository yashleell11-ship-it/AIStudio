import { afterEach, describe, expect, it } from "vitest";
import {
  isPageProxyUrl,
  pageImageUrlForBox,
  pageRequestWidth,
  pageUrlWidth,
  readerColumnWidth,
  withPageWidth,
} from "./page-url";

const API = "http://127.0.0.1:8000";
const PAGE = `${API}/sources/asura/pages/vol1%2Fp551/image`;

// vitest runs in the `node` environment (vitest.config.ts), so `window` is
// absent unless a test puts one there — which is the server-render path the
// builder has to stay pure and deterministic on.
const mutableGlobal = globalThis as unknown as Record<string, unknown>;

function browser(innerWidth: number, devicePixelRatio: number): void {
  mutableGlobal.window = { innerWidth, devicePixelRatio };
}

afterEach(() => {
  delete mutableGlobal.window;
});

describe("isPageProxyUrl", () => {
  it("matches the page-bytes route in relative and absolute form", () => {
    expect(isPageProxyUrl(PAGE)).toBe(true);
    expect(isPageProxyUrl("/sources/asura/pages/p1/image")).toBe(true);
    expect(isPageProxyUrl("/api/sources/asura/pages/p1/image?w=800")).toBe(true);
  });

  it("leaves everything that is not ours alone", () => {
    // Several connectors hand back the source's own CDN URL; a `?w=` there is
    // useless at best and breaks a signed link at worst.
    expect(isPageProxyUrl("https://cdn.example/a.webp")).toBe(false);
    expect(isPageProxyUrl(`${API}/sources/asura/series/x/cover`)).toBe(false);
    expect(isPageProxyUrl(`${API}/sources/asura/pages/p1`)).toBe(false);
  });
});

describe("readerColumnWidth", () => {
  it("is the reader column, not the viewport", () => {
    browser(1920, 1);
    expect(readerColumnWidth()).toBe(768);
    browser(390, 3);
    expect(readerColumnWidth()).toBe(390);
  });
});

describe("pageRequestWidth", () => {
  it("asks for the box in device pixels", () => {
    browser(1920, 1);
    expect(pageRequestWidth(768)).toBe(768);
    browser(390, 3);
    expect(pageRequestWidth(390)).toBe(1170);
  });

  it("clamps the ratio at 3 and the request inside the route's declared range", () => {
    browser(1920, 4);
    expect(pageRequestWidth(768)).toBe(2304);
    expect(pageRequestWidth(9999)).toBe(10000);
    expect(pageRequestWidth(0)).toBeNull();
  });
});

describe("withPageWidth", () => {
  it("appends the width, preserving any query already there", () => {
    browser(1920, 1);
    expect(withPageWidth(PAGE, 768)).toBe(`${PAGE}?w=768`);
    expect(withPageWidth(`${PAGE}?v=2`, 768)).toBe(`${PAGE}?v=2&w=768`);
  });

  it("falls back to serving the original whenever it cannot help", () => {
    browser(1920, 1);
    const upstream = "https://cdn.example/a.webp";
    expect(withPageWidth(upstream, 768)).toBe(upstream);
    expect(withPageWidth(PAGE, 0)).toBe(PAGE);
  });

  it("is deterministic without a window, so nothing re-fetches on hydration", () => {
    expect(withPageWidth(PAGE, 768)).toBe(`${PAGE}?w=1536`);
    expect(withPageWidth(PAGE, 768)).toBe(withPageWidth(PAGE, 768));
  });
});

describe("pageUrlWidth", () => {
  it("reads back the width a URL was built with", () => {
    expect(pageUrlWidth(`${PAGE}?w=768`)).toBe(768);
    expect(pageUrlWidth(`${PAGE}?v=2&w=1170`)).toBe(1170);
    expect(pageUrlWidth(PAGE)).toBeNull();
    expect(pageUrlWidth(`${PAGE}?w=abc`)).toBeNull();
  });
});

describe("pageImageUrlForBox", () => {
  it("returns the URL BYTE-IDENTICAL when the baked width covers the box", () => {
    browser(1920, 1);
    const baked = withPageWidth(PAGE, 768);
    // Identity, not just equality: this string is the prefetch key, the `<img>`
    // src, the offline cache key and a `memo` boundary.
    expect(pageImageUrlForBox(baked, 768)).toBe(baked);
    expect(pageImageUrlForBox(baked, 400)).toBe(baked);
  });

  it("drops to the original rather than asking below display size", () => {
    browser(1920, 1);
    const baked = withPageWidth(PAGE, 768);
    // Zoomed to 2x, the page paints at 1536 CSS px. Serving it 768 would be
    // visibly soft, and the reader reads manga.
    expect(pageImageUrlForBox(baked, 1536)).toBe(PAGE);
  });

  it("keeps any other query when it drops the width", () => {
    browser(1920, 1);
    expect(pageImageUrlForBox(`${PAGE}?v=2&w=768`, 1536)).toBe(`${PAGE}?v=2`);
  });

  it("leaves a URL that never carried a width alone", () => {
    browser(1920, 1);
    const upstream = "https://cdn.example/a.webp";
    expect(pageImageUrlForBox(upstream, 4000)).toBe(upstream);
    expect(pageImageUrlForBox(PAGE, 4000)).toBe(PAGE);
  });

  it("is inert on a phone, where the strip is already narrower than the ask", () => {
    // DPR 3 on a 390px column asks for 1170 device px; sources publish strips
    // at 720-800, so the server refuses the resize and serves the original.
    // Nothing here changes that — this only decides what is REQUESTED.
    browser(390, 3);
    const baked = withPageWidth(PAGE, readerColumnWidth());
    expect(baked).toBe(`${PAGE}?w=1170`);
    expect(pageImageUrlForBox(baked, 390)).toBe(baked);
  });
});
