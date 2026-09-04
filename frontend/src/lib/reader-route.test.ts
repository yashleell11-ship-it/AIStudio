import { describe, expect, it } from "vitest";
import {
  isImmersiveNovelPath,
  isImmersivePath,
  isImmersiveReaderPath,
} from "./reader-route";

describe("isImmersiveReaderPath", () => {
  it("is true for a source-native chapter route", () => {
    expect(isImmersiveReaderPath("/reader/asura/nano-machine/ch-210")).toBe(true);
    // Encoded keys containing slashes still match (single encoded segments).
    expect(
      isImmersiveReaderPath("/reader/asura/series%2Fnano-machine/ch%2F210"),
    ).toBe(true);
    // Catch-all chapter key with real slashes.
    expect(isImmersiveReaderPath("/reader/mangadex/abc/vol/1/ch/2")).toBe(true);
  });

  it("is false for the bare /reader landing and everything outside the reader", () => {
    expect(isImmersiveReaderPath("/reader")).toBe(false);
    expect(isImmersiveReaderPath("/reader/")).toBe(false);
    expect(isImmersiveReaderPath("/reader/asura")).toBe(false);
    expect(isImmersiveReaderPath("/library")).toBe(false);
    expect(isImmersiveReaderPath("/sources/asura/series/x")).toBe(false);
  });
});

describe("isImmersiveNovelPath", () => {
  it("is true for a novel chapter route", () => {
    expect(isImmersiveNovelPath("/novels/royalroad/12345/ch-1")).toBe(true);
    expect(isImmersiveNovelPath("/novels/archiveorg/pg%2F1342/vol/1/ch/2")).toBe(true);
  });

  it("is false for the manga reader and for everything short of a chapter", () => {
    expect(isImmersiveNovelPath("/novels")).toBe(false);
    expect(isImmersiveNovelPath("/novels/royalroad")).toBe(false);
    expect(isImmersiveNovelPath("/reader/asura/nano-machine/ch-210")).toBe(false);
    expect(isImmersiveNovelPath("/library")).toBe(false);
  });
});

describe("isImmersivePath", () => {
  it("covers both readers, and nothing else", () => {
    expect(isImmersivePath("/reader/asura/nano-machine/ch-210")).toBe(true);
    expect(isImmersivePath("/novels/royalroad/12345/ch-1")).toBe(true);
    expect(isImmersivePath("/reader")).toBe(false);
    expect(isImmersivePath("/novels")).toBe(false);
    expect(isImmersivePath("/sources/royalroad/series/12345")).toBe(false);
  });
});
