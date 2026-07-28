import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import {
  discardLegacyRecentSearches,
  getRecentSearchesSnapshot,
  nextRecentSearches,
  parseRecentSearches,
  readRecentSearches,
  writeRecentSearch,
} from "./recent-searches";

const LEGACY_KEY = "manhwamaniacs:recent-searches";
const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };

let storage = installMemoryStorage();

beforeEach(() => {
  storage = installMemoryStorage();
  setStorageScope(null);
});

afterEach(() => {
  setStorageScope(null);
  uninstallMemoryStorage();
});

describe("nextRecentSearches", () => {
  it("puts the newest term first", () => {
    expect(nextRecentSearches(["romance"], "horror")).toEqual(["horror", "romance"]);
  });

  it("moves a repeated term back to the front instead of duplicating it", () => {
    // Matched case-insensitively, kept as just typed: the chip should read back
    // the way the user last searched.
    expect(nextRecentSearches(["romance", "horror"], "Romance")).toEqual([
      "Romance",
      "horror",
    ]);
  });

  it("keeps only the four most recent", () => {
    expect(nextRecentSearches(["a1", "b2", "c3", "d4"], "e5")).toEqual([
      "e5",
      "a1",
      "b2",
      "c3",
    ]);
  });

  it("ignores terms too short to have been searched", () => {
    expect(nextRecentSearches(["romance"], " a ")).toEqual(["romance"]);
  });

  it("stores the trimmed term", () => {
    expect(nextRecentSearches([], "  solo leveling ")).toEqual(["solo leveling"]);
  });
});

describe("parseRecentSearches", () => {
  it("survives a corrupt value", () => {
    expect(parseRecentSearches("{not json")).toEqual([]);
  });

  it("drops non-string entries", () => {
    expect(parseRecentSearches(JSON.stringify(["romance", 7, null]))).toEqual([
      "romance",
    ]);
  });
});

describe("profile isolation", () => {
  it("does not show one profile's searches to another", () => {
    setStorageScope(ALICE);
    writeRecentSearch("solo leveling");
    expect(readRecentSearches()).toEqual(["solo leveling"]);

    setStorageScope(BOB);
    expect(readRecentSearches()).toEqual([]);
  });

  it("gives each profile its own list back after a switch", () => {
    setStorageScope(ALICE);
    writeRecentSearch("solo leveling");
    setStorageScope(BOB);
    writeRecentSearch("tower of god");
    setStorageScope(ALICE);

    expect(readRecentSearches()).toEqual(["solo leveling"]);
  });

  it("reads nothing while no profile is active", () => {
    storage.setItem(LEGACY_KEY, JSON.stringify(["device-global"]));
    setStorageScope(null);

    expect(readRecentSearches()).toEqual([]);
  });

  it("writes nothing while no profile is active", () => {
    setStorageScope(null);
    writeRecentSearch("solo leveling");

    expect(storage.keys()).toEqual([]);
  });
});

describe("getRecentSearchesSnapshot", () => {
  it("returns the same reference until the list changes", () => {
    setStorageScope(ALICE);
    writeRecentSearch("solo leveling");

    expect(getRecentSearchesSnapshot()).toBe(getRecentSearchesSnapshot());
  });

  it("re-reads when the profile changes", () => {
    setStorageScope(ALICE);
    writeRecentSearch("solo leveling");
    const alices = getRecentSearchesSnapshot();

    setStorageScope(BOB);

    expect(getRecentSearchesSnapshot()).not.toBe(alices);
    expect(getRecentSearchesSnapshot()).toEqual([]);
  });
});

describe("discardLegacyRecentSearches", () => {
  it("drops the pre-scoping list rather than giving it to a profile", () => {
    storage.setItem(LEGACY_KEY, JSON.stringify(["an adult title"]));

    setStorageScope(ALICE);
    discardLegacyRecentSearches();

    expect(storage.getItem(LEGACY_KEY)).toBeNull();
    expect(readRecentSearches()).toEqual([]);
  });
});
