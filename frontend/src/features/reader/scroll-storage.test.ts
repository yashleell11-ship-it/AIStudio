import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { setStorageScope } from "@/lib/scoped-storage";
import {
  installMemoryStorage,
  uninstallMemoryStorage,
} from "@/lib/scoped-storage.testing";
import { readScrollPosition, writeScrollPosition } from "./scroll-storage";

describe("per-profile scroll position", () => {
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
    writeScrollPosition("ch-1", 4200);
    expect(readScrollPosition("ch-1")).toBe(4200);

    setStorageScope(BOB);
    expect(readScrollPosition("ch-1")).toBeNull();
  });

  it("keeps each profile's place across a switch and back", () => {
    setStorageScope(ALICE);
    writeScrollPosition("ch-1", 4200);
    setStorageScope(BOB);
    writeScrollPosition("ch-1", 100);
    setStorageScope(ALICE);
    expect(readScrollPosition("ch-1")).toBe(4200);
  });

  it("stores nothing when no profile is active", () => {
    writeScrollPosition("ch-1", 4200);
    expect(readScrollPosition("ch-1")).toBeNull();
  });
});
