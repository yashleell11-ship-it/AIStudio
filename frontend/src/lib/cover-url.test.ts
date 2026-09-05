import { afterEach, describe, expect, it } from "vitest";
import { libraryCoverUrl, seriesCoverUrl } from "@/features/library/api";
import { densityCoverSizes, LIBRARY_DENSITIES } from "@/features/library/density";
import { sourceImageUrl } from "@/features/sources/api";
import { SHELF_PLATE_SIZES } from "@/features/novels/shelf";
import { coverCssWidth, withCoverWidth } from "./cover-url";
import { imagePixelRatio } from "./device-pixels";

const API = "http://127.0.0.1:8000";
const COVER = `${API}/sources/mangadex/series/abc/cover`;

// vitest runs in the `node` environment (see vitest.config.ts), so `window` is
// absent unless a test puts one there — which is exactly the server-render path
// the builders have to stay pure on.
const mutableGlobal = globalThis as unknown as Record<string, unknown>;

function browser(innerWidth: number, devicePixelRatio: number): void {
  mutableGlobal.window = { innerWidth, devicePixelRatio };
}

afterEach(() => {
  delete mutableGlobal.window;
});

describe("coverCssWidth", () => {
  it("reads a bare length in either unit", () => {
    expect(coverCssWidth("64px", 375)).toBe(64);
    expect(coverCssWidth("50vw", 375)).toBe(187.5);
  });

  it("takes the first branch whose condition holds", () => {
    const sizes = "(max-width: 639px) 112px, 176px";
    expect(coverCssWidth(sizes, 375)).toBe(112);
    expect(coverCssWidth(sizes, 639)).toBe(112);
    expect(coverCssWidth(sizes, 640)).toBe(176);
  });

  it("understands min-width as well as max-width", () => {
    expect(coverCssWidth("(min-width: 1024px) 220px, 120px", 1280)).toBe(220);
    expect(coverCssWidth("(min-width: 1024px) 220px, 120px", 800)).toBe(120);
  });

  it("resolves the calc() form a grid cell actually is", () => {
    // `grid-cols-2 gap-4` inside `p-6`: (375 - 48 - 16) / 2.
    expect(coverCssWidth("calc(50vw - 32px)", 375)).toBe(155.5);
    expect(coverCssWidth("calc(50vw + 10px)", 400)).toBe(210);
  });

  it("returns null for syntax it does not model, rather than a guess", () => {
    // A wrong guess is a permanently blurry cover that nothing reports; null
    // means the caller falls back to the original image, which is only heavy.
    expect(coverCssWidth("min(50vw, 300px)", 375)).toBeNull();
    expect(coverCssWidth("50em", 375)).toBeNull();
    expect(coverCssWidth("(max-height: 500px) 100px, 50px", 375)).toBeNull();
    expect(coverCssWidth("", 375)).toBeNull();
  });

  it("returns null when no branch matches", () => {
    expect(coverCssWidth("(min-width: 1024px) 220px", 800)).toBeNull();
  });
});

describe("imagePixelRatio", () => {
  it("clamps at 3, above which the server's ladder tops out anyway", () => {
    browser(375, 4);
    expect(imagePixelRatio()).toBe(3);
    browser(375, 2.625);
    expect(imagePixelRatio()).toBe(2.625);
  });

  it("falls back to 1 for a ratio the browser reports as nonsense", () => {
    browser(375, 0);
    expect(imagePixelRatio()).toBe(1);
    browser(375, Number.NaN);
    expect(imagePixelRatio()).toBe(1);
  });
});

describe("withCoverWidth", () => {
  it("asks for the box in device pixels", () => {
    browser(375, 3);
    // 155.5 CSS px x DPR 3, rounded — sent verbatim for the server to snap.
    expect(withCoverWidth(COVER, "calc(50vw - 32px)")).toBe(`${COVER}?w=467`);
  });

  it("sends the width it means and never a width off the server's ladder", () => {
    // The client must not mirror `image_resize.COVER_WIDTHS`: two copies of the
    // ladder drift, and snapping is the server's job precisely so the client
    // can ask for anything. 44 x 2 is not a rung, and is sent as-is.
    browser(1280, 2);
    expect(withCoverWidth(COVER, "44px")).toBe(`${COVER}?w=88`);
    expect(withCoverWidth(COVER, "80px")).toBe(`${COVER}?w=160`);
  });

  it("leaves anything that is not the cover proxy alone", () => {
    browser(375, 3);
    const upstream = "https://uploads.mangadex.org/covers/abc/def.jpg";
    expect(withCoverWidth(upstream, "64px")).toBe(upstream);
    const icon = `${API}/sources/mangadex/icon.png`;
    expect(withCoverWidth(icon, "32px")).toBe(icon);
  });

  it("leaves the URL alone with no hint, or an unusable one", () => {
    browser(375, 3);
    expect(withCoverWidth(COVER, undefined)).toBe(COVER);
    expect(withCoverWidth(COVER, null)).toBe(COVER);
    expect(withCoverWidth(COVER, "")).toBe(COVER);
    expect(withCoverWidth(COVER, "min(50vw, 300px)")).toBe(COVER);
  });

  it("keeps the width inside the range the route declares for `w`", () => {
    // Past 10000 the route answers 422, which is a broken cover rather than a
    // heavy one. The server snaps anything over its top rung down by itself.
    browser(3840, 3);
    expect(withCoverWidth(COVER, "100vw")).toBe(`${COVER}?w=10000`);
  });

  it("appends to a URL that already carries a query", () => {
    browser(1280, 1);
    expect(withCoverWidth(`${COVER}?v=2`, "64px")).toBe(`${COVER}?v=2&w=64`);
  });

  it("recognises the relative proxy path the browse payload carries", () => {
    browser(1280, 1);
    expect(withCoverWidth("/api/sources/bato/series/x/cover", "64px")).toBe(
      "/api/sources/bato/series/x/cover?w=64",
    );
  });
});

describe("without a window", () => {
  // No cover-bearing view is server-rendered with rows in hand — they all fetch
  // through react-query in the browser — but the builders still have to be pure
  // functions off the main thread, and they have to be DETERMINISTIC: a value
  // an effect upgraded after mount would rewrite every cover URL on the page
  // and fetch every cover a second time.
  it("resolves to the documented fallback rather than throwing", () => {
    expect(imagePixelRatio()).toBe(2);
    expect(withCoverWidth(COVER, "64px")).toBe(`${COVER}?w=128`);
  });

  it("is stable across calls, so nothing re-fetches on hydration", () => {
    const sizes = densityCoverSizes("comfortable");
    expect(withCoverWidth(COVER, sizes)).toBe(withCoverWidth(COVER, sizes));
  });
});

describe("the URL builders", () => {
  it("adds the width to a relative library cover path", () => {
    browser(375, 2);
    expect(libraryCoverUrl("/sources/bato/series/x/cover", "64px")).toBe(
      `${API}/sources/bato/series/x/cover?w=128`,
    );
  });

  it("does not touch a library cover the backend gave as an upstream URL", () => {
    browser(375, 2);
    const upstream = "https://cdn.example.com/cover.jpg";
    expect(libraryCoverUrl(upstream, "64px")).toBe(upstream);
  });

  it("keeps the un-sized form for callers that have no box in mind", () => {
    browser(375, 2);
    expect(libraryCoverUrl("/sources/bato/series/x/cover")).toBe(
      `${API}/sources/bato/series/x/cover`,
    );
    expect(sourceImageUrl("/sources/bato/icon.png")).toBe(`${API}/sources/bato/icon.png`);
  });

  it("encodes the series key before the width is appended", () => {
    browser(375, 2);
    expect(seriesCoverUrl({ sourceId: "bato", seriesKey: "a/b" }, "64px")).toBe(
      `${API}/sources/bato/series/a%2Fb/cover?w=128`,
    );
  });
});

describe("every cover hint the app ships", () => {
  // The hints are written as CSS `sizes` strings at the call sites, and a hint
  // this module cannot read silently falls back to the full-resolution cover.
  // Each of these is the string one of those call sites passes.
  const HINTS = [
    ...LIBRARY_DENSITIES.map(densityCoverSizes),
    SHELF_PLATE_SIZES,
    "(max-width: 639px) calc(33.33vw - 21px), 180px", // FollowedSeriesCard
    "(max-width: 639px) calc(50vw - 32px), 260px", // SourceSeriesCard
    "(max-width: 639px) 112px, 176px", // ContinueReading hero
    "(max-width: 639px) 144px, 168px", // NovelSeriesDetailView plate
    "(max-width: 1023px) 200px, 220px", // SourceSeriesDetailView poster
    "220px", // SeriesDetailView poster
    "170px", // SourceBrowseLoading tile
    "80px", // GlobalSearchResultCard
    "70px", // ContinueReading rail
    "64px", // SeriesCard list row
    "44px", // StatisticsView row
    "32px", // CollectionDetailView picker, CommandPalette row
  ];

  it("parses at a phone width and at a desktop width", () => {
    for (const hint of HINTS) {
      expect(coverCssWidth(hint, 375), hint).toBeGreaterThan(0);
      expect(coverCssWidth(hint, 1920), hint).toBeGreaterThan(0);
    }
  });

  it("keeps a phone's grid cells inside the box they are painted into", () => {
    // The regression this guards: a round `50vw` for a cell that is really
    // `calc(50vw - 32px)` claims 187px on a 375px phone, and 187 x DPR 3 lands
    // a rung further up the server's ladder (720 rather than 480) for every
    // cover on the screen.
    expect(coverCssWidth(densityCoverSizes("comfortable"), 375)).toBeLessThan(160);
    expect(coverCssWidth("(max-width: 639px) calc(50vw - 32px), 260px", 375)).toBeLessThan(
      160,
    );
  });
});
