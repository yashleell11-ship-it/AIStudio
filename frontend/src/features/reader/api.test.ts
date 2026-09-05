import { describe, expect, it } from "vitest";
import { manifestToChapterContent, type ChapterManifest } from "./api";

const manifest: ChapterManifest = {
  source_id: "asura",
  series_key: "series/nano-machine",
  chapter_key: "ch/210",
  chapter_number: 210,
  page_count: 3,
  pages: [
    { number: 1, url: "https://cdn.example/a.webp" },
    { number: 2, url: "/sources/asura/pages/b/image", width: 720, height: 14668 },
    { number: 3, url: "sources/asura/pages/c/image" },
  ],
  prev: "ch/209",
  next: "ch/211",
};

describe("manifestToChapterContent", () => {
  it("builds a renderable chapter synchronously from the manifest alone", () => {
    const chapter = manifestToChapterContent(manifest);
    expect(chapter).toMatchObject({
      sourceId: "asura",
      seriesKey: "series/nano-machine",
      chapterKey: "ch/210",
      chapterNumber: 210,
      title: "Chapter 210",
      pageCount: 3,
      previousChapterKey: "ch/209",
      nextChapterKey: "ch/211",
    });
    expect(chapter.pages).toHaveLength(3);
  });

  it("keeps absolute page URLs and resolves relative ones against the API base", () => {
    const [a, b, c] = manifestToChapterContent(manifest).pages;
    // Not our route, so no `?w=` is appended: a query on a source's own CDN URL
    // ranges from useless to breaking a signed link.
    expect(a.imageUrl).toBe("https://cdn.example/a.webp");
    expect(b.imageUrl).toMatch(/\/sources\/asura\/pages\/b\/image\?w=\d+$/);
    expect(b.imageUrl).toMatch(/^https?:\/\//);
    expect(c.imageUrl).toMatch(/\/sources\/asura\/pages\/c\/image\?w=\d+$/);
  });

  it("asks the page proxy for the reader column in device pixels", () => {
    // Off the main thread the builder still has to be a pure, DETERMINISTIC
    // function: a width settled in an effect after mount would rewrite every
    // page URL and fetch the whole chapter a second time.
    const [, b] = manifestToChapterContent(manifest).pages;
    expect(b.imageUrl).toMatch(/\?w=1536$/);
    expect(manifestToChapterContent(manifest).pages[1].imageUrl).toBe(b.imageUrl);
  });

  it("gives each page a stable id and a 1-based number", () => {
    const pages = manifestToChapterContent(manifest).pages;
    expect(pages.map((p) => p.number)).toEqual([1, 2, 3]);
    expect(new Set(pages.map((p) => p.id)).size).toBe(3);
  });

  it("carries the source's page dimensions through, null when it has none", () => {
    // The whole reason the manifest reports them: without these the reader has
    // to guess a webtoon strip's extent from a fixed aspect ratio.
    const pages = manifestToChapterContent(manifest).pages;
    expect(pages[1]).toMatchObject({ width: 720, height: 14668 });
    expect(pages[0]).toMatchObject({ width: null, height: null });
    expect(pages[2]).toMatchObject({ width: null, height: null });
  });

  it("falls back to a generic title when the chapter has no number", () => {
    const chapter = manifestToChapterContent({ ...manifest, chapter_number: null });
    expect(chapter.title).toBe("Chapter");
    expect(chapter.chapterNumber).toBeNull();
  });

  it("reports null adjacent keys at the ends of a series", () => {
    const chapter = manifestToChapterContent({ ...manifest, prev: null, next: null });
    expect(chapter.previousChapterKey).toBeNull();
    expect(chapter.nextChapterKey).toBeNull();
  });
});
