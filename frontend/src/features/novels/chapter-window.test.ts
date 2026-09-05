import { describe, expect, it } from "vitest";
import {
  NOVEL_WINDOW_CAP,
  boundedWindow,
  collectChapterWindow,
} from "./chapter-window";
import type {
  NovelChapterPayload,
  NovelChapterWindowItem,
  NovelChapterWindowPayload,
} from "./types";

function chapter(
  chapterKey: string,
  paragraphs: string[] = ["The first line."],
): NovelChapterPayload {
  return {
    source_id: "novelbin",
    series_key: "/book/a-record-of-a-mortal",
    chapter_key: chapterKey,
    title: null,
    chapter_number: 1,
    paragraphs,
    prev: null,
    next: null,
    word_count: 3,
  };
}

function ok(chapterKey: string, paragraphs?: string[]): NovelChapterWindowItem {
  return {
    chapter_key: chapterKey,
    status: "ok",
    chapter: chapter(chapterKey, paragraphs),
    error: null,
  };
}

function failed(chapterKey: string, message?: string): NovelChapterWindowItem {
  return {
    chapter_key: chapterKey,
    status: "error",
    chapter: null,
    error:
      message === undefined
        ? null
        : { code: "novel_chapter_unavailable", status: 502, message },
  };
}

function windowOf(items: NovelChapterWindowItem[]): NovelChapterWindowPayload {
  const okCount = items.filter((item) => item.status === "ok").length;
  return {
    source_id: "novelbin",
    series_key: "/book/a-record-of-a-mortal",
    max_chapters: NOVEL_WINDOW_CAP,
    requested: items.length,
    ok_count: okCount,
    failed_count: items.length - okCount,
    items,
  };
}

describe("boundedWindow", () => {
  it("passes a window that already fits", () => {
    expect(boundedWindow(["a", "b", "c"])).toEqual(["a", "b", "c"]);
  });

  it("clamps to the cap rather than earning a 413", () => {
    // Over the cap fails the WHOLE window, so a caller holding a long book has
    // to stride. Clamping means no caller has to remember that.
    const keys = Array.from({ length: NOVEL_WINDOW_CAP + 7 }, (_, i) => `c${i}`);
    expect(boundedWindow(keys)).toHaveLength(NOVEL_WINDOW_CAP);
    expect(boundedWindow(keys)[0]).toBe("c0");
  });

  it("honours a smaller cap the server reported", () => {
    expect(boundedWindow(["a", "b", "c", "d"], 2)).toEqual(["a", "b"]);
  });

  it("never lets a nonsense cap silence the window", () => {
    // One chapter still beats none, and a deployment that reports 0 or a
    // negative must not turn every warm into a no-op.
    expect(boundedWindow(["a", "b"], 0)).toEqual(["a"]);
    expect(boundedWindow(["a", "b"], -5)).toEqual(["a"]);
    expect(boundedWindow(["a", "b"], Number.NaN)).toEqual(["a", "b"]);
  });

  it("does not let a server raise the cap past what the client will send", () => {
    const keys = Array.from({ length: 40 }, (_, i) => `c${i}`);
    expect(boundedWindow(keys, 100)).toHaveLength(NOVEL_WINDOW_CAP);
  });

  it("passes an empty request through untouched", () => {
    expect(boundedWindow([])).toEqual([]);
  });
});

describe("collectChapterWindow", () => {
  it("splits a partial window into what arrived and what did not", () => {
    // Partial success is the NORMAL case, not an edge one: the window fans out
    // to one upstream scrape per miss and any of them can fail on its own.
    const keys = ["c1", "c2", "c3"];
    const { chapters, failures } = collectChapterWindow(
      keys,
      windowOf([ok("c1"), failed("c2", "The source did not return this chapter."), ok("c3")]),
    );

    expect([...chapters.keys()]).toEqual(["c1", "c3"]);
    expect(chapters.get("c1")?.paragraphs).toEqual(["The first line."]);
    expect(failures.get("c2")).toBe("The source did not return this chapter.");
    expect(failures.has("c1")).toBe(false);
  });

  it("treats a chapter with no prose as a failure, not as a chapter", () => {
    // Caching an empty chapter would make the emptiness stick for the whole
    // stale window. The phone applies the same rule, so both clients agree on
    // what "the window did not give me this one" means.
    const { chapters, failures } = collectChapterWindow(["c1"], windowOf([ok("c1", [])]));

    expect(chapters.size).toBe(0);
    expect(failures.get("c1")).toBe("This chapter has no text.");
  });

  it("still names a failure the server described only by status", () => {
    const { failures } = collectChapterWindow(["c1"], windowOf([failed("c1")]));
    expect(failures.get("c1")).toBe("This chapter could not be fetched.");
  });

  it("keys results by the spelling the caller asked with", () => {
    // The server percent-decodes the keys it is given, so a key carrying a
    // literal `%` comes back spelled differently — and the caller's cache and
    // chapter list both use the caller's spelling. Items arrive in request
    // order, one per key, so position is the pairing.
    const requested = ["/c/ch-100%2Fb", "/c/ch-101"];
    const { chapters } = collectChapterWindow(
      requested,
      windowOf([ok("/c/ch-100/b"), ok("/c/ch-101")]),
    );

    expect([...chapters.keys()]).toEqual(requested);
  });

  it("falls back to the echoed key when the answer does not line up", () => {
    // Not a shape the server produces today. If it ever did, pairing by
    // position would file chapter 2's text under chapter 1's key — a wrong
    // chapter is far worse than a missing one.
    const { chapters } = collectChapterWindow(["c1", "c2"], windowOf([ok("c2")]));
    expect([...chapters.keys()]).toEqual(["c2"]);
  });

  it("ignores an item with no key at all", () => {
    const payload = windowOf([ok("c1"), ok("c2")]);
    payload.items[1] = { ...payload.items[1], chapter_key: "" };
    // Length still matches, so position keys it — the blank is only reached
    // through the unaligned path, which is what this pins.
    const { chapters } = collectChapterWindow(["c1"], payload);
    expect([...chapters.keys()]).toEqual(["c1"]);
  });

  it("reads an answer with no items as nothing rather than throwing", () => {
    // A warm must never raise at a reader, so the collector cannot be the
    // thing that throws on a shape it did not expect.
    expect(collectChapterWindow(["c1"], windowOf([])).chapters.size).toBe(0);
    const malformed = { items: undefined } as unknown as NovelChapterWindowPayload;
    expect(collectChapterWindow(["c1"], malformed).failures.size).toBe(0);
  });
});
