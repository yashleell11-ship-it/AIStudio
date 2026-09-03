import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import {
  applyReaderPreferences,
  DEFAULT_READER_PREFERENCES,
  normalizeReaderPreferences,
  readerSeriesKey,
  readReaderPreferences,
  readReaderPreferencesRaw,
  writeReaderPreferences,
  type ReaderPreferencesStore,
} from "./preferences";

describe("readerSeriesKey", () => {
  it("namespaces local series apart from source series", () => {
    expect(readerSeriesKey(null, 42)).toBe("local:42");
    expect(readerSeriesKey("asurascans", "solo-leveling")).toBe(
      "asurascans:solo-leveling",
    );
  });
});

describe("normalizeReaderPreferences", () => {
  it("defaults anything missing or unrecognised", () => {
    expect(normalizeReaderPreferences(undefined)).toEqual(DEFAULT_READER_PREFERENCES);
    expect(normalizeReaderPreferences("nonsense")).toEqual(DEFAULT_READER_PREFERENCES);
    expect(normalizeReaderPreferences({ readingMode: "spiral", fitMode: 3 })).toEqual(
      DEFAULT_READER_PREFERENCES,
    );
  });

  it("keeps valid values", () => {
    expect(
      normalizeReaderPreferences({
        readingMode: "double",
        fitMode: "height",
        direction: "rtl",
        zoom: 1.5,
        autoScrollSpeed: 8,
      }),
    ).toEqual({
      readingMode: "double",
      fitMode: "height",
      direction: "rtl",
      zoom: 1.5,
      autoScrollSpeed: 8,
    });
  });

  it("clamps a stored zoom that is out of range", () => {
    expect(normalizeReaderPreferences({ zoom: 99 }).zoom).toBe(3);
    expect(normalizeReaderPreferences({ zoom: 0 }).zoom).toBe(0.5);
  });

  it("clamps a stored auto-scroll speed that is out of range", () => {
    expect(normalizeReaderPreferences({ autoScrollSpeed: 99 }).autoScrollSpeed).toBe(10);
    expect(normalizeReaderPreferences({ autoScrollSpeed: 0 }).autoScrollSpeed).toBe(1);
    expect(normalizeReaderPreferences({ autoScrollSpeed: "fast" }).autoScrollSpeed).toBe(
      DEFAULT_READER_PREFERENCES.autoScrollSpeed,
    );
  });
});

describe("applyReaderPreferences", () => {
  it("patches one series without touching the others", () => {
    const store: ReaderPreferencesStore = {
      "local:1": {
        readingMode: "double",
        fitMode: "height",
        direction: "rtl",
        zoom: 1,
        autoScrollSpeed: 5,
      },
    };

    const next = applyReaderPreferences(store, "asurascans:x", { readingMode: "single" });

    expect(next["local:1"]).toEqual(store["local:1"]);
    expect(next["asurascans:x"]).toEqual({
      ...DEFAULT_READER_PREFERENCES,
      readingMode: "single",
    });
  });

  it("merges onto the series' existing choice rather than replacing it", () => {
    const store = applyReaderPreferences({}, "local:1", {
      readingMode: "double",
      direction: "rtl",
    });
    const next = applyReaderPreferences(store, "local:1", { zoom: 1.4 });

    expect(next["local:1"]).toEqual({
      readingMode: "double",
      fitMode: "width",
      direction: "rtl",
      zoom: 1.4,
      autoScrollSpeed: DEFAULT_READER_PREFERENCES.autoScrollSpeed,
    });
  });

  it("does not mutate the store it was given", () => {
    const store: ReaderPreferencesStore = {};
    applyReaderPreferences(store, "local:1", { readingMode: "single" });
    expect(store).toEqual({});
  });
});

describe("per-profile reader preferences", () => {
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

  it("does not let one profile inherit another's reading mode", () => {
    setStorageScope(ALICE);
    writeReaderPreferences("local:1", { readingMode: "double", direction: "rtl" });
    expect(readReaderPreferences("local:1").readingMode).toBe("double");

    // Bob gets the defaults, not Alice's right-to-left spreads.
    setStorageScope(BOB);
    expect(readReaderPreferences("local:1")).toEqual(DEFAULT_READER_PREFERENCES);
  });

  it("keeps each profile's choice across a switch and back", () => {
    setStorageScope(ALICE);
    writeReaderPreferences("local:1", { readingMode: "double" });
    setStorageScope(BOB);
    writeReaderPreferences("local:1", { readingMode: "single" });

    setStorageScope(ALICE);
    expect(readReaderPreferences("local:1").readingMode).toBe("double");
    setStorageScope(BOB);
    expect(readReaderPreferences("local:1").readingMode).toBe("single");
  });

  it("stores nothing at all when no profile is active", () => {
    writeReaderPreferences("local:1", { readingMode: "double" });
    expect(readReaderPreferences("local:1")).toEqual(DEFAULT_READER_PREFERENCES);
    // and nothing was parked under a bare key for a later profile to inherit
    expect(readReaderPreferencesRaw()).toBeNull();
  });

  it("remembers auto-scroll speed per series, not globally", () => {
    setStorageScope(ALICE);
    // A slow-panel manhwa gets a slow speed...
    writeReaderPreferences("local:1", { autoScrollSpeed: 2 });
    // ...and a fast gag strip gets a fast one, without disturbing the first.
    writeReaderPreferences("local:2", { autoScrollSpeed: 9 });

    expect(readReaderPreferences("local:1").autoScrollSpeed).toBe(2);
    expect(readReaderPreferences("local:2").autoScrollSpeed).toBe(9);
  });

  it("does not let one profile inherit another's auto-scroll speed", () => {
    setStorageScope(ALICE);
    writeReaderPreferences("local:1", { autoScrollSpeed: 8 });

    setStorageScope(BOB);
    expect(readReaderPreferences("local:1").autoScrollSpeed).toBe(
      DEFAULT_READER_PREFERENCES.autoScrollSpeed,
    );
  });
});
