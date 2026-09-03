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
    { number: 2, url: "/sources/asura/pages/b/image" },
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
    expect(a.imageUrl).toBe("https://cdn.example/a.webp");
    expect(b.imageUrl).toMatch(/\/sources\/asura\/pages\/b\/image$/);
    expect(b.imageUrl).toMatch(/^https?:\/\//);
    expect(c.imageUrl).toMatch(/\/sources\/asura\/pages\/c\/image$/);
  });

  it("gives each page a stable id and a 1-based number, dimensions unknown", () => {
    const pages = manifestToChapterContent(manifest).pages;
    expect(pages.map((p) => p.number)).toEqual([1, 2, 3]);
    expect(new Set(pages.map((p) => p.id)).size).toBe(3);
    expect(pages[0]).toMatchObject({ width: null, height: null });
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
