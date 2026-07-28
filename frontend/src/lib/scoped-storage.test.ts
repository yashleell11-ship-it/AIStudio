import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  claimLegacyValue,
  discardLegacyValue,
  readScopedString,
  scopedStorageKey,
  setStorageScope,
  subscribeStorageScope,
  writeScopedString,
} from "./scoped-storage";
import { installMemoryStorage, uninstallMemoryStorage } from "./scoped-storage.testing";

const ALICE = { userId: 1, profileId: 10 };
const BOB = { userId: 1, profileId: 11 };
const BASE = "mm.thing";

let storage = installMemoryStorage();

beforeEach(() => {
  storage = installMemoryStorage();
  setStorageScope(null);
});

afterEach(() => {
  setStorageScope(null);
  uninstallMemoryStorage();
});

describe("scopedStorageKey", () => {
  it("names the owner in the key", () => {
    expect(scopedStorageKey(BASE, ALICE)).toBe("mm.thing::u1:p10");
  });

  it("separates profiles of the same account", () => {
    expect(scopedStorageKey(BASE, ALICE)).not.toBe(scopedStorageKey(BASE, BOB));
  });

  it("separates accounts, so a reused profile id could not merge them", () => {
    expect(scopedStorageKey(BASE, { userId: 2, profileId: 10 })).not.toBe(
      scopedStorageKey(BASE, ALICE),
    );
  });

  it("has no key at all without a scope", () => {
    expect(scopedStorageKey(BASE, null)).toBeNull();
  });
});

describe("scoped reads and writes", () => {
  it("does not read one profile's value under another", () => {
    setStorageScope(ALICE);
    writeScopedString(BASE, "alice's");

    setStorageScope(BOB);
    expect(readScopedString(BASE)).toBeNull();
  });

  it("keeps each profile's value across a switch and back", () => {
    setStorageScope(ALICE);
    writeScopedString(BASE, "alice's");
    setStorageScope(BOB);
    writeScopedString(BASE, "bob's");
    setStorageScope(ALICE);

    expect(readScopedString(BASE)).toBe("alice's");
  });

  it("reads nothing with no active profile rather than a global blob", () => {
    storage.setItem(BASE, "device-global");
    setStorageScope(null);

    expect(readScopedString(BASE)).toBeNull();
  });

  it("drops writes with no active profile instead of parking them globally", () => {
    setStorageScope(null);
    writeScopedString(BASE, "nobody's");

    expect(storage.keys()).toEqual([]);
  });
});

describe("setStorageScope", () => {
  it("notifies subscribers so stores re-read under the new keys", () => {
    let notifications = 0;
    const unsubscribe = subscribeStorageScope(() => {
      notifications += 1;
    });

    setStorageScope(ALICE);
    setStorageScope(BOB);
    unsubscribe();
    setStorageScope(ALICE);

    expect(notifications).toBe(2);
  });

  it("stays quiet when the same scope is republished", () => {
    setStorageScope(ALICE);
    let notifications = 0;
    subscribeStorageScope(() => {
      notifications += 1;
    });

    setStorageScope({ ...ALICE });

    expect(notifications).toBe(0);
  });
});

describe("claimLegacyValue", () => {
  it("hands a pre-scoping value to the first claimant only", () => {
    storage.setItem(BASE, "pre-profiles");

    setStorageScope(ALICE);
    expect(claimLegacyValue(BASE)).toBe("pre-profiles");

    setStorageScope(BOB);
    expect(claimLegacyValue(BASE)).toBeNull();
  });

  it("leaves an unowned value alone rather than destroying it", () => {
    storage.setItem(BASE, "pre-profiles");
    setStorageScope(null);

    expect(claimLegacyValue(BASE)).toBeNull();
    expect(storage.getItem(BASE)).toBe("pre-profiles");
  });
});

describe("discardLegacyValue", () => {
  it("removes the value without reading it", () => {
    storage.setItem(BASE, "pre-profiles");

    discardLegacyValue(BASE);

    expect(storage.getItem(BASE)).toBeNull();
  });
});
