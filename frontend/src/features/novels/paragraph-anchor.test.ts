import { describe, expect, it } from "vitest";
import { captureParagraphAnchor, restoreParagraphAnchor } from "./paragraph-anchor";

/** Four paragraphs, 100px apart, in a 500px-tall column. */
const OFFSETS = [0, 100, 200, 300];
const CONTENT_END = 500;

describe("captureParagraphAnchor", () => {
  it("names the paragraph the reading line is in, 1-based", () => {
    expect(captureParagraphAnchor(OFFSETS, 240, CONTENT_END)).toEqual({
      index: 3,
      fraction: 0.4,
      total: 4,
    });
  });

  it("records the head of a paragraph as fraction zero", () => {
    expect(captureParagraphAnchor(OFFSETS, 200, CONTENT_END)).toEqual({
      index: 3,
      fraction: 0,
      total: 4,
    });
  });

  it("measures the last paragraph against the end of the content", () => {
    // The last paragraph runs 300 → 500, so halfway is 400.
    expect(captureParagraphAnchor(OFFSETS, 400, CONTENT_END)).toEqual({
      index: 4,
      fraction: 0.5,
      total: 4,
    });
  });

  it("is null before anything is measured, rather than claiming paragraph 1 of 0", () => {
    expect(captureParagraphAnchor([], 240, CONTENT_END)).toBeNull();
  });

  it("reads a line above the first paragraph as the very start", () => {
    expect(captureParagraphAnchor(OFFSETS, -40, CONTENT_END)).toEqual({
      index: 1,
      fraction: 0,
      total: 4,
    });
  });
});

describe("restoreParagraphAnchor", () => {
  it("is the exact inverse of a capture when nothing changed", () => {
    const captured = captureParagraphAnchor(OFFSETS, 247, CONTENT_END);
    expect(captured).not.toBeNull();
    const restored = restoreParagraphAnchor(OFFSETS, captured!, CONTENT_END);
    expect(restored).toEqual({ point: 247, stale: false });
  });

  it("round-trips a position in the last paragraph too", () => {
    const captured = captureParagraphAnchor(OFFSETS, 462, CONTENT_END);
    expect(restoreParagraphAnchor(OFFSETS, captured!, CONTENT_END)).toEqual({
      point: 462,
      stale: false,
    });
  });

  it("lands on the nearest surviving paragraph when the text was re-split", () => {
    // Bookmarked paragraph 4; the chapter now has two.
    const shorter = [0, 100];
    expect(restoreParagraphAnchor(shorter, { index: 4, fraction: 0.5 }, 250)).toEqual({
      point: 250,
      stale: true,
    });
  });

  it("does not report stale for an anchor that still fits", () => {
    expect(
      restoreParagraphAnchor(OFFSETS, { index: 4, fraction: 0 }, CONTENT_END),
    ).toEqual({ point: 300, stale: false });
  });

  it("is null with nothing measured, so the caller leaves the scroll alone", () => {
    expect(restoreParagraphAnchor([], { index: 2, fraction: 0.5 }, 500)).toBeNull();
  });
});
