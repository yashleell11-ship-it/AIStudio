import { describe, expect, it } from "vitest";
import {
  buildCarouselSlides,
  nextSlideIndex,
  sourceHue,
  COVERS_PER_SLIDE,
} from "./loading-carousel";

describe("buildCarouselSlides", () => {
  it("groups items into slides of the default size", () => {
    const slides = buildCarouselSlides([1, 2, 3, 4, 5, 6]);
    expect(slides).toEqual([
      [1, 2, 3],
      [4, 5, 6],
    ]);
  });

  it("keeps the remainder in a final short slide", () => {
    const slides = buildCarouselSlides([1, 2, 3, 4], COVERS_PER_SLIDE);
    expect(slides).toEqual([[1, 2, 3], [4]]);
  });

  it("returns a single slide when there are fewer items than a slide", () => {
    expect(buildCarouselSlides([1, 2])).toEqual([[1, 2]]);
  });

  it("returns no slides for an empty list", () => {
    expect(buildCarouselSlides([])).toEqual([]);
  });

  it("honours a custom slide size", () => {
    expect(buildCarouselSlides([1, 2, 3, 4, 5], 2)).toEqual([
      [1, 2],
      [3, 4],
      [5],
    ]);
  });

  it("rejects a non-positive slide size", () => {
    expect(() => buildCarouselSlides([1], 0)).toThrow();
  });
});

describe("nextSlideIndex", () => {
  it("advances to the next slide", () => {
    expect(nextSlideIndex(0, 3)).toBe(1);
    expect(nextSlideIndex(1, 3)).toBe(2);
  });

  it("wraps back to the first slide after the last", () => {
    expect(nextSlideIndex(2, 3)).toBe(0);
  });

  it("stays at zero when there are no slides", () => {
    expect(nextSlideIndex(0, 0)).toBe(0);
  });
});

describe("sourceHue", () => {
  it("is deterministic for a given id", () => {
    expect(sourceHue("toonily")).toBe(sourceHue("toonily"));
  });

  it("stays within the 0-359 hue range", () => {
    for (const id of ["toonily", "mangakatana", "demonicscans", "a", ""]) {
      const hue = sourceHue(id);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThanOrEqual(359);
    }
  });
});
