import { describe, expect, it } from "vitest";
import { isImmersiveReaderPath } from "./reader-route";

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
