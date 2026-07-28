import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import {
  DEFAULT_LIBRARY_DENSITY,
  densityCoverSizes,
  densityGridClassName,
  getLibraryDensitySnapshot,
  parseLibraryDensity,
  readLibraryDensity,
  writeLibraryDensity,
} from "./density";

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

describe("parseLibraryDensity", () => {
  it("accepts the three real densities", () => {
    expect(parseLibraryDensity("comfortable")).toBe("comfortable");
    expect(parseLibraryDensity("compact")).toBe("compact");
    expect(parseLibraryDensity("list")).toBe("list");
  });

  it("falls back for an unset or corrupt value", () => {
    expect(parseLibraryDensity(null)).toBe(DEFAULT_LIBRARY_DENSITY);
    expect(parseLibraryDensity("grid")).toBe(DEFAULT_LIBRARY_DENSITY);
  });
});

describe("profile isolation", () => {
  it("does not show one profile's density to another", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("compact");
    expect(readLibraryDensity()).toBe("compact");

    setStorageScope(BOB);
    expect(readLibraryDensity()).toBe(DEFAULT_LIBRARY_DENSITY);
  });

  it("gives each profile its own choice back after a switch", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("compact");
    setStorageScope(BOB);
    writeLibraryDensity("list");
    setStorageScope(ALICE);

    expect(readLibraryDensity()).toBe("compact");
  });

  it("writes nothing device-global while no profile is active", () => {
    setStorageScope(null);
    writeLibraryDensity("compact");

    expect(storage.keys()).toEqual([]);
    expect(readLibraryDensity()).toBe(DEFAULT_LIBRARY_DENSITY);
  });

  it("namespaces the key by user and profile", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("list");

    expect(storage.keys()).toEqual(["manhwamaniacs:library-density::u1:p10"]);
  });
});

describe("getLibraryDensitySnapshot", () => {
  it("re-reads when the profile changes", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("compact");
    expect(getLibraryDensitySnapshot()).toBe("compact");

    setStorageScope(BOB);
    expect(getLibraryDensitySnapshot()).toBe(DEFAULT_LIBRARY_DENSITY);
  });

  it("re-reads when the value changes in the same profile", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("compact");
    expect(getLibraryDensitySnapshot()).toBe("compact");

    writeLibraryDensity("list");
    expect(getLibraryDensitySnapshot()).toBe("list");
  });
});

describe("layout classes", () => {
  it("gives list its own stacking layout rather than a grid", () => {
    expect(densityGridClassName("list")).not.toContain("grid-cols");
    expect(densityGridClassName("compact")).toContain("grid-cols");
    expect(densityGridClassName("comfortable")).toContain("grid-cols");
  });

  it("asks for smaller images the more it packs in", () => {
    expect(densityCoverSizes("list")).toBe("64px");
    expect(densityCoverSizes("compact")).not.toBe(densityCoverSizes("comfortable"));
  });
});
