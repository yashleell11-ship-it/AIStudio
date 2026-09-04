import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { scopedStorageKey, setStorageScope, writeScopedString } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { readReaderPosition, writeReaderPosition } from "./scroll-storage";

describe("per-profile reading position", () => {
  const ALICE = { userId: 1, profileId: 10 };
  const BOB = { userId: 1, profileId: 11 };

  beforeEach(() => {
    installMemoryStorage();
    setStorageScope(null);
  });

  afterEach(() => {
    setStorageScope(null);
    uninstallMemoryStorage();
  });

  it("does not move one profile's place from another's reading", () => {
    setStorageScope(ALICE);
    writeReaderPosition("ch-1", { page: 4, offset: 200 });
    expect(readReaderPosition("ch-1")).toEqual({ page: 4, offset: 200 });

    setStorageScope(BOB);
    expect(readReaderPosition("ch-1")).toBeNull();
  });

  it("keeps each profile's place across a switch and back", () => {
    setStorageScope(ALICE);
    writeReaderPosition("ch-1", { page: 4, offset: 200 });
    setStorageScope(BOB);
    writeReaderPosition("ch-1", { page: 1, offset: 100 });
    setStorageScope(ALICE);
    expect(readReaderPosition("ch-1")).toEqual({ page: 4, offset: 200 });
  });

  it("stores nothing when no profile is active", () => {
    writeReaderPosition("ch-1", { page: 4, offset: 200 });
    expect(readReaderPosition("ch-1")).toBeNull();
  });

  it("rounds and clamps what it is given", () => {
    setStorageScope(ALICE);
    writeReaderPosition("ch-1", { page: 0, offset: -40 });
    expect(readReaderPosition("ch-1")).toEqual({ page: 1, offset: 0 });
    writeReaderPosition("ch-2", { page: 3.6, offset: 12.4 });
    expect(readReaderPosition("ch-2")).toEqual({ page: 4, offset: 12 });
  });

  it("still reads a position written in the old pixel-only format", () => {
    setStorageScope(ALICE);
    // What the single-chapter reader wrote: a distance from the chapter's
    // start, which is exactly "page one, that far in".
    writeScopedString("manhwamaniacs-reader-scroll:ch-1", "4200");
    expect(readReaderPosition("ch-1")).toEqual({ page: 1, offset: 4200 });
  });

  it("ignores a stored value that is not a position at all", () => {
    setStorageScope(ALICE);
    writeScopedString("manhwamaniacs-reader-scroll:ch-1", "not-a-number");
    expect(readReaderPosition("ch-1")).toBeNull();
    writeScopedString("manhwamaniacs-reader-scroll:ch-2", "-12");
    expect(readReaderPosition("ch-2")).toBeNull();
    // Namespacing is the store's, so the key it reads is the key it wrote.
    expect(scopedStorageKey("manhwamaniacs-reader-scroll:ch-1", ALICE)).toContain(
      "u1:p10",
    );
  });

  it("has nothing to say about a chapter it never stored", () => {
    setStorageScope(ALICE);
    expect(readReaderPosition("never-opened")).toBeNull();
  });
});
