import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { writeDesignPreset } from "@/features/preferences/preset-store";
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

describe("the design preset seeds the layout", () => {
  /**
   * "Poster grid, list, or compact rows" is a preset's decision, not a
   * constant. The contract is the same one the theme system uses for the OS
   * preference: the preset seeds a profile that has never chosen, and an
   * explicit choice wins from then on.
   */
  it("opens on the preset's layout when the profile has never chosen", () => {
    setStorageScope(ALICE);
    expect(readLibraryDensity()).toBe("comfortable");

    writeDesignPreset("editorial");
    expect(readLibraryDensity()).toBe("list");

    writeDesignPreset("compact");
    expect(readLibraryDensity()).toBe("compact");
  });

  it("lets an explicit choice outlive a preset change", () => {
    setStorageScope(ALICE);
    writeLibraryDensity("comfortable");
    writeDesignPreset("compact");
    // Chose the poster grid, then switched to a density-first design. The
    // design does not get to overrule a decision that was already made.
    expect(readLibraryDensity()).toBe("comfortable");
  });

  it("re-resolves the snapshot when the preset changes", () => {
    // What makes a preset apply live: `useSyncExternalStore` compares by
    // reference, so a cached snapshot that ignored the preset would leave the
    // library in its old layout until something else invalidated it.
    setStorageScope(ALICE);
    expect(getLibraryDensitySnapshot()).toBe("comfortable");
    writeDesignPreset("editorial");
    expect(getLibraryDensitySnapshot()).toBe("list");
    writeDesignPreset("signature");
    expect(getLibraryDensitySnapshot()).toBe("comfortable");
  });

  it("keeps one profile's preset out of another's library", () => {
    setStorageScope(ALICE);
    writeDesignPreset("compact");
    expect(readLibraryDensity()).toBe("compact");

    setStorageScope(BOB);
    expect(readLibraryDensity()).toBe(DEFAULT_LIBRARY_DENSITY);
  });
});
