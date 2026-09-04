import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { MAX_DIMMER, MAX_WARMTH } from "./overlay";
import { writeDesignPreset } from "@/features/preferences/preset-store";
import {
  DEFAULT_READER_SETTINGS,
  getReaderSettingsSnapshot,
  parseReaderSettings,
  readReaderSettings,
  writeReaderSettings,
} from "./reader-settings";

describe("parseReaderSettings", () => {
  it("defaults everything for null, empty or malformed input", () => {
    expect(parseReaderSettings(null)).toEqual(DEFAULT_READER_SETTINGS);
    expect(parseReaderSettings("")).toEqual(DEFAULT_READER_SETTINGS);
    expect(parseReaderSettings("not json")).toEqual(DEFAULT_READER_SETTINGS);
  });

  it("keeps valid values", () => {
    expect(
      parseReaderSettings(
        JSON.stringify({
          pageGap: true,
          cinema: true,
          dimmer: 0.4,
          warmth: 0.2,
          pageTransition: true,
          tapZones: { left: "retreat", center: "toggle", right: "advance" },
        }),
      ),
    ).toEqual({
      pageGap: true,
      cinema: true,
      dimmer: 0.4,
      warmth: 0.2,
      pageTransition: true,
      tapZones: { left: "retreat", center: "toggle", right: "advance" },
    });
  });

  it("clamps a stored dimmer/warmth that is out of range", () => {
    expect(parseReaderSettings(JSON.stringify({ dimmer: 5 })).dimmer).toBe(MAX_DIMMER);
    expect(parseReaderSettings(JSON.stringify({ dimmer: -5 })).dimmer).toBe(0);
    expect(parseReaderSettings(JSON.stringify({ warmth: 5 })).warmth).toBe(MAX_WARMTH);
    expect(parseReaderSettings(JSON.stringify({ warmth: -5 })).warmth).toBe(0);
  });

  it("falls back to null for a malformed or partial tap-zone config", () => {
    expect(parseReaderSettings(JSON.stringify({ tapZones: "nonsense" })).tapZones).toBeNull();
    expect(
      parseReaderSettings(JSON.stringify({ tapZones: { left: "advance" } })).tapZones,
    ).toBeNull();
    expect(
      parseReaderSettings(
        JSON.stringify({ tapZones: { left: "spiral", center: "toggle", right: "advance" } }),
      ).tapZones,
    ).toBeNull();
  });
});

describe("per-profile reader settings", () => {
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

  it("persists dimmer, warmth and tap zones for the active profile", () => {
    setStorageScope(ALICE);
    writeReaderSettings({ dimmer: 0.6, warmth: 0.3 });
    writeReaderSettings({ tapZones: { left: "advance", center: "toggle", right: "retreat" } });

    const settings = readReaderSettings();
    expect(settings.dimmer).toBe(0.6);
    expect(settings.warmth).toBe(0.3);
    expect(settings.tapZones).toEqual({ left: "advance", center: "toggle", right: "retreat" });
  });

  it("does not let one profile inherit another's brightness setup", () => {
    setStorageScope(ALICE);
    writeReaderSettings({ dimmer: 0.8, warmth: 0.5 });

    setStorageScope(BOB);
    expect(readReaderSettings()).toEqual(DEFAULT_READER_SETTINGS);
  });

  it("stores nothing at all when no profile is active", () => {
    writeReaderSettings({ dimmer: 0.9 });
    expect(readReaderSettings()).toEqual(DEFAULT_READER_SETTINGS);
  });
});

describe("the design preset seeds the reader chrome", () => {
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

  /**
   * "How much furniture the reader shows" is a preset axis, and the Cinema
   * preset exists to say "none of it". Same contract as the library layout:
   * the preset supplies the default, an explicit toggle wins for good.
   */
  it("opens the reader in cinema mode under the Cinema preset", () => {
    setStorageScope(ALICE);
    expect(readReaderSettings().cinema).toBe(false);

    writeDesignPreset("cinema");
    expect(readReaderSettings().cinema).toBe(true);

    writeDesignPreset("editorial");
    expect(readReaderSettings().cinema).toBe(false);
  });

  it("leaves every other reader setting alone", () => {
    setStorageScope(ALICE);
    writeDesignPreset("cinema");
    expect(readReaderSettings()).toEqual({
      ...DEFAULT_READER_SETTINGS,
      cinema: true,
    });
  });

  it("lets an explicit toggle outlive a preset change", () => {
    setStorageScope(ALICE);
    // Turned cinema mode off by hand, then adopted the design that defaults it
    // on. The stored `false` is a decision and has to survive.
    writeReaderSettings({ cinema: false });
    writeDesignPreset("cinema");
    expect(readReaderSettings().cinema).toBe(false);
  });

  it("re-resolves the snapshot when the preset changes", () => {
    setStorageScope(ALICE);
    expect(getReaderSettingsSnapshot().cinema).toBe(false);
    writeDesignPreset("cinema");
    expect(getReaderSettingsSnapshot().cinema).toBe(true);
  });

  it("keeps one profile's preset out of another's reader", () => {
    setStorageScope(ALICE);
    writeDesignPreset("cinema");
    setStorageScope(BOB);
    expect(readReaderSettings().cinema).toBe(false);
  });
});
