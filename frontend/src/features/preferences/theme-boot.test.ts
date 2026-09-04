import { describe, expect, it } from "vitest";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/features/profiles/storage-key";
import { scopedStorageKey } from "@/lib/scoped-storage";
import { THEME_BOOT_SOURCE } from "./theme-boot-source";
import { READING_THEME_STORAGE_BASE } from "./theme";

/**
 * The boot script runs before the bundle, before React, and before any error
 * boundary exists. Nothing on the page can report it failing, and the symptom
 * of a bug — a palette that flashes, or the wrong one entirely — is the kind of
 * thing that gets shrugged off as "the browser being slow". So it is executed
 * here for real, against a fake `localStorage` and `document`, exactly as the
 * browser would run it.
 */

interface Store {
  [key: string]: string;
}

/** Run the script over a snapshot of localStorage; returns the attribute set. */
function boot(store: Store, options: { throwOnRead?: boolean } = {}): string | null {
  const keys = Object.keys(store);
  const localStorage = {
    get length() {
      return keys.length;
    },
    key: (index: number) => keys[index] ?? null,
    getItem: (key: string) => {
      if (options.throwOnRead) throw new Error("storage is blocked");
      return Object.prototype.hasOwnProperty.call(store, key) ? store[key] : null;
    },
  };
  let applied: string | null = null;
  const document = {
    documentElement: {
      setAttribute: (name: string, value: string) => {
        if (name === "data-theme") applied = value;
      },
    },
  };
  // The source is a function BODY (it uses bare `return`), which is why it is
  // exported separately from the IIFE the page gets.
  const run = new Function("localStorage", "document", THEME_BOOT_SOURCE) as (
    ls: unknown,
    doc: unknown,
  ) => void;
  run(localStorage, document);
  return applied;
}

/** localStorage as it looks for a signed-in viewer on profile `profileId`. */
function storeFor(
  profileId: number,
  entries: Record<string, string> = {},
): Store {
  return {
    [ACTIVE_PROFILE_STORAGE_KEY]: JSON.stringify({
      state: { activeProfile: { id: profileId, name: "Yash" } },
      version: 0,
    }),
    ...entries,
  };
}

const themeKey = (userId: number, profileId: number) =>
  scopedStorageKey(READING_THEME_STORAGE_BASE, { userId, profileId }) as string;

describe("theme boot script", () => {
  it("applies the active profile's stored palette", () => {
    expect(boot(storeFor(7, { [themeKey(1, 7)]: "gruvbox-dark-hard" }))).toBe(
      "gruvbox-dark-hard",
    );
  });

  it("finds the key without knowing the user id", () => {
    // The whole reason it scans: at boot only the profile id is recoverable.
    expect(boot(storeFor(3, { [themeKey(4321, 3)]: "nord" }))).toBe("nord");
  });

  it("does not read another profile's choice", () => {
    // The visible failure this prevents: pick up a shared laptop, open the app,
    // and see the previous persona's palette for a frame.
    const store = storeFor(2, {
      [themeKey(1, 1)]: "catppuccin-latte",
      [themeKey(1, 9)]: "sepia",
    });
    expect(boot(store)).toBeNull();
  });

  it("is not fooled by a profile id that is a suffix of another", () => {
    // ":p1" must not match the key for profile 21.
    const store = storeFor(1, { [themeKey(1, 21)]: "dracula" });
    expect(boot(store)).toBeNull();
  });

  it("leaves the attribute alone when no profile is selected", () => {
    // Login and the profile picker: globals.css follows prefers-color-scheme
    // instead, which agrees with what `initialReadingTheme` will pick.
    expect(boot({})).toBeNull();
    expect(
      boot({
        [ACTIVE_PROFILE_STORAGE_KEY]: JSON.stringify({ state: {}, version: 0 }),
      }),
    ).toBeNull();
  });

  it("ignores a stored value that is not a shipped palette", () => {
    // A palette dropped from the curation list, or storage edited by hand.
    expect(boot(storeFor(5, { [themeKey(1, 5)]: "solarized-dark" }))).toBeNull();
    expect(boot(storeFor(5, { [themeKey(1, 5)]: "" }))).toBeNull();
  });

  it("tolerates whitespace, as the parser does", () => {
    expect(boot(storeFor(5, { [themeKey(1, 5)]: "  monokai\n" }))).toBe("monokai");
  });

  it("survives corrupt profile JSON", () => {
    expect(boot({ [ACTIVE_PROFILE_STORAGE_KEY]: "{not json" })).toBeNull();
  });

  it("survives storage throwing outright", () => {
    // Locked-down browsers throw on access rather than returning null. A
    // palette is never worth a blank page.
    expect(() => boot(storeFor(1, { [themeKey(1, 1)]: "nord" }), { throwOnRead: true })).not.toThrow();
  });
});
