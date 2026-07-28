import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import {
  adoptLegacySourceProgress,
  applyProgressRemap,
  getSourceChapterProgress,
  getSourceSeriesProgress,
  mergeLegacyProgress,
  setSourceChapterProgress,
} from "./source-progress";
import type { SourceChapterProgress, SourceProgressStore } from "./source-progress";

const FROM = { source: "asura", seriesId: "old-slug" };
const TO = { source: "bato", seriesId: "new-slug" };

const LEGACY_KEY = "mm.source-progress";
const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };

function progress(page: number, updatedAt: string): SourceChapterProgress {
  return { page, pageCount: 20, completed: page >= 20, updatedAt };
}

describe("applyProgressRemap", () => {
  it("carries progress onto the target's chapter ids", () => {
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(20, "2026-07-01T00:00:00Z"),
      "asura:old-slug:c2": progress(7, "2026-07-02T00:00:00Z"),
    };

    const { store: next, moved } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
      { from_chapter_id: "c2", to_chapter_id: "bato-2" },
    ]);

    expect(moved).toBe(2);
    expect(next["bato:new-slug:bato-1"]).toEqual(store["asura:old-slug:c1"]);
    expect(next["bato:new-slug:bato-2"]?.page).toBe(7);
  });

  it("leaves the old records in place, so migrating back loses nothing", () => {
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(20, "2026-07-01T00:00:00Z"),
    };
    const { store: next } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
    ]);
    expect(next["asura:old-slug:c1"]).toBeDefined();
  });

  it("skips chapters with no equivalent on the target", () => {
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(4, "2026-07-01T00:00:00Z"),
    };
    const { store: next, moved } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: null },
    ]);
    expect(moved).toBe(0);
    expect(Object.keys(next)).toEqual(["asura:old-slug:c1"]);
  });

  it("skips mapped chapters that were never read", () => {
    const { store: next, moved } = applyProgressRemap({}, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
    ]);
    expect(moved).toBe(0);
    expect(next).toEqual({});
  });

  it("never overwrites newer progress already recorded on the target", () => {
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(3, "2026-07-01T00:00:00Z"),
      "bato:new-slug:bato-1": progress(18, "2026-07-20T00:00:00Z"),
    };
    const { store: next, moved } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
    ]);
    expect(moved).toBe(0);
    expect(next["bato:new-slug:bato-1"]?.page).toBe(18);
  });

  it("keeps the most recently read chapter when two collapse onto one target", () => {
    // Nearest-match can map two old chapters onto a single target chapter.
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(3, "2026-07-01T00:00:00Z"),
      "asura:old-slug:c2": progress(11, "2026-07-05T00:00:00Z"),
    };
    const { store: next } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
      { from_chapter_id: "c2", to_chapter_id: "bato-1" },
    ]);
    expect(next["bato:new-slug:bato-1"]?.page).toBe(11);
  });

  it("does not mutate the store it was given", () => {
    const store: SourceProgressStore = {
      "asura:old-slug:c1": progress(3, "2026-07-01T00:00:00Z"),
    };
    applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
    ]);
    expect(Object.keys(store)).toEqual(["asura:old-slug:c1"]);
  });

  it("ignores progress belonging to a different series on the same source", () => {
    const store: SourceProgressStore = {
      "asura:other-slug:c1": progress(9, "2026-07-01T00:00:00Z"),
    };
    const { store: next, moved } = applyProgressRemap(store, FROM, TO, [
      { from_chapter_id: "c1", to_chapter_id: "bato-1" },
    ]);
    expect(moved).toBe(0);
    expect(next).toEqual(store);
  });
});

describe("mergeLegacyProgress", () => {
  it("takes records the scope does not have", () => {
    const { store, adopted } = mergeLegacyProgress(
      {},
      { "asura:old-slug:c1": progress(7, "2026-07-01T00:00:00Z") },
    );
    expect(adopted).toBe(1);
    expect(store["asura:old-slug:c1"]?.page).toBe(7);
  });

  it("never walks a scoped record back to an older legacy one", () => {
    const scoped: SourceProgressStore = {
      "asura:old-slug:c1": progress(18, "2026-07-20T00:00:00Z"),
    };
    const { store, adopted } = mergeLegacyProgress(scoped, {
      "asura:old-slug:c1": progress(3, "2026-07-01T00:00:00Z"),
    });
    expect(adopted).toBe(0);
    expect(store["asura:old-slug:c1"]?.page).toBe(18);
  });

  it("does not mutate the store it was given", () => {
    const scoped: SourceProgressStore = {};
    mergeLegacyProgress(scoped, {
      "asura:old-slug:c1": progress(7, "2026-07-01T00:00:00Z"),
    });
    expect(scoped).toEqual({});
  });
});

describe("per-profile storage", () => {
  let storage = installMemoryStorage();

  beforeEach(() => {
    storage = installMemoryStorage();
    setStorageScope(null);
  });

  afterEach(() => {
    setStorageScope(null);
    uninstallMemoryStorage();
  });

  it("does not read one profile's reading place under another", () => {
    setStorageScope(ALICE);
    setSourceChapterProgress("asura", "old-slug", "c1", { page: 7, pageCount: 20 });
    expect(getSourceChapterProgress("asura", "old-slug", "c1")?.page).toBe(7);

    setStorageScope(BOB);
    expect(getSourceChapterProgress("asura", "old-slug", "c1")).toBeNull();
    expect(getSourceSeriesProgress("asura", "old-slug")).toEqual({});
  });

  it("keeps each profile's place across a switch and back", () => {
    setStorageScope(ALICE);
    setSourceChapterProgress("asura", "old-slug", "c1", { page: 7, pageCount: 20 });
    setStorageScope(BOB);
    setSourceChapterProgress("asura", "old-slug", "c1", { page: 2, pageCount: 20 });
    setStorageScope(ALICE);

    expect(getSourceChapterProgress("asura", "old-slug", "c1")?.page).toBe(7);
  });

  it("reads nothing with no active profile rather than a shared store", () => {
    storage.setItem(
      LEGACY_KEY,
      JSON.stringify({ "asura:old-slug:c1": progress(7, "2026-07-01T00:00:00Z") }),
    );
    setStorageScope(null);

    expect(getSourceChapterProgress("asura", "old-slug", "c1")).toBeNull();
  });

  it("writes nothing with no active profile", () => {
    setStorageScope(null);
    setSourceChapterProgress("asura", "old-slug", "c1", { page: 7, pageCount: 20 });

    expect(storage.keys()).toEqual([]);
  });
});

describe("adoptLegacySourceProgress", () => {
  let storage = installMemoryStorage();

  beforeEach(() => {
    storage = installMemoryStorage();
    setStorageScope(null);
  });

  afterEach(() => {
    setStorageScope(null);
    uninstallMemoryStorage();
  });

  it("gives the pre-scoping positions to the first profile, and no other", () => {
    storage.setItem(
      LEGACY_KEY,
      JSON.stringify({ "asura:old-slug:c1": progress(7, "2026-07-01T00:00:00Z") }),
    );

    setStorageScope(ALICE);
    expect(adoptLegacySourceProgress()).toBe(1);
    expect(getSourceChapterProgress("asura", "old-slug", "c1")?.page).toBe(7);

    setStorageScope(BOB);
    expect(adoptLegacySourceProgress()).toBe(0);
    expect(getSourceChapterProgress("asura", "old-slug", "c1")).toBeNull();
  });

  it("waits for a profile instead of destroying an unowned blob", () => {
    storage.setItem(
      LEGACY_KEY,
      JSON.stringify({ "asura:old-slug:c1": progress(7, "2026-07-01T00:00:00Z") }),
    );
    setStorageScope(null);

    expect(adoptLegacySourceProgress()).toBe(0);
    expect(storage.getItem(LEGACY_KEY)).not.toBeNull();
  });

  it("does not walk a profile's own newer place back", () => {
    setStorageScope(ALICE);
    setSourceChapterProgress("asura", "old-slug", "c1", { page: 18, pageCount: 20 });
    storage.setItem(
      LEGACY_KEY,
      JSON.stringify({ "asura:old-slug:c1": progress(3, "2020-01-01T00:00:00Z") }),
    );

    expect(adoptLegacySourceProgress()).toBe(0);
    expect(getSourceChapterProgress("asura", "old-slug", "c1")?.page).toBe(18);
  });

  it("is a no-op on a device that never had the unscoped key", () => {
    setStorageScope(ALICE);
    expect(adoptLegacySourceProgress()).toBe(0);
  });
});
