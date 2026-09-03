import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { MAX_DIMMER, MAX_WARMTH } from "./overlay";
import {
  DEFAULT_READER_SETTINGS,
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
