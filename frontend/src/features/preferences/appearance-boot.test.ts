import { describe, expect, it } from "vitest";
import { ACTIVE_PROFILE_STORAGE_KEY } from "@/features/profiles/storage-key";
import { scopedStorageKey } from "@/lib/scoped-storage";
import { APPEARANCE_BOOT_SOURCE } from "./appearance-boot-source";
import { DESIGN_PRESET_STORAGE_BASE } from "./presets";
import { READING_THEME_STORAGE_BASE } from "./theme";

/**
 * The boot script runs before the bundle, before React, and before any error
 * boundary exists. Nothing on the page can report it failing, and the symptom
 * of a bug — a palette that flashes, or the wrong one entirely — is the kind of
 * thing that gets shrugged off as "the browser being slow". So it is executed
 * here for real, against a fake `localStorage` and `document`, exactly as the
 * browser would run it.
 *
 * It carries two channels — the palette on `data-theme` and the design preset
 * on `data-preset` — over one scan of localStorage, so every case below asserts
 * on both: they share the profile lookup, the suffix match and the single
 * `try`, and a regression in any of those would take out both halves of the
 * appearance at once.
 */

interface Store {
  [key: string]: string;
}

interface Applied {
  theme: string | null;
  preset: string | null;
}

/** Run the script over a snapshot of localStorage; returns what it stamped. */
function bootBoth(
  store: Store,
  options: { throwOnRead?: boolean; pathname?: string } = {},
): Applied {
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
  const applied: Applied = { theme: null, preset: null };
  const document = {
    documentElement: {
      setAttribute: (name: string, value: string) => {
        if (name === "data-theme") applied.theme = value;
        if (name === "data-preset") applied.preset = value;
      },
    },
  };
  // The source is a function BODY (it uses bare `return`), which is why it is
  // exported separately from the IIFE the page gets.
  const run = new Function(
    "localStorage",
    "document",
    "location",
    APPEARANCE_BOOT_SOURCE,
  ) as (ls: unknown, doc: unknown, loc: unknown) => void;
  run(localStorage, document, { pathname: options.pathname ?? "/library" });
  return applied;
}

/** The palette the script applied, or `null`. */
function boot(
  store: Store,
  options: { throwOnRead?: boolean; pathname?: string } = {},
): string | null {
  return bootBoth(store, options).theme;
}

/** The design preset the script applied, or `null`. */
function bootPreset(
  store: Store,
  options: { throwOnRead?: boolean; pathname?: string } = {},
): string | null {
  return bootBoth(store, options).preset;
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

const presetKey = (userId: number, profileId: number) =>
  scopedStorageKey(DESIGN_PRESET_STORAGE_BASE, { userId, profileId }) as string;

describe("appearance boot script — palette", () => {
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

  it("declines on the auth screens, which belong to nobody yet", () => {
    // A persisted profile id outlives its session. Applying its palette on
    // /login would paint for someone who is not signed in, and the store —
    // which needs the session too — would then repaint to the OS preference.
    const store = storeFor(4, { [themeKey(1, 4)]: "nord" });
    expect(boot(store, { pathname: "/login" })).toBeNull();
    expect(boot(store, { pathname: "/register" })).toBeNull();
    expect(boot(store, { pathname: "/register/" })).toBeNull();
    // …but every other route is fair game, including the profile picker.
    expect(boot(store, { pathname: "/profiles" })).toBe("nord");
    expect(boot(store, { pathname: "/login/extra" })).toBe("nord");
  });

  it("survives storage throwing outright", () => {
    // Locked-down browsers throw on access rather than returning null. A
    // palette is never worth a blank page.
    expect(() => boot(storeFor(1, { [themeKey(1, 1)]: "nord" }), { throwOnRead: true })).not.toThrow();
  });
});

describe("appearance boot script — design preset", () => {
  it("applies the active profile's stored preset", () => {
    expect(bootPreset(storeFor(7, { [presetKey(1, 7)]: "editorial" }))).toBe(
      "editorial",
    );
  });

  it("finds the key without knowing the user id", () => {
    expect(bootPreset(storeFor(3, { [presetKey(4321, 3)]: "cinema" }))).toBe("cinema");
  });

  it("does not read another profile's choice", () => {
    const store = storeFor(2, {
      [presetKey(1, 1)]: "compact",
      [presetKey(1, 9)]: "flat",
    });
    expect(bootPreset(store)).toBeNull();
  });

  it("is not fooled by a profile id that is a suffix of another", () => {
    expect(bootPreset(storeFor(1, { [presetKey(1, 21)]: "cinema" }))).toBeNull();
  });

  it("ignores a stored value that is not a shipped preset", () => {
    // "eclipse" is the name the design brief used for the default preset and
    // is now a THEME id — precisely the value a hand-edited store might hold.
    expect(bootPreset(storeFor(5, { [presetKey(1, 5)]: "eclipse" }))).toBeNull();
    expect(bootPreset(storeFor(5, { [presetKey(1, 5)]: "" }))).toBeNull();
  });

  it("tolerates whitespace, as the parser does", () => {
    expect(bootPreset(storeFor(5, { [presetKey(1, 5)]: " compact\n" }))).toBe("compact");
  });

  it("leaves the attribute alone when no profile is selected", () => {
    // With no attribute the bare `:root` shape defaults apply, which ARE
    // Signature — so there is nothing to correct later.
    expect(bootPreset({})).toBeNull();
  });

  it("declines on the auth screens, which belong to nobody yet", () => {
    const store = storeFor(4, { [presetKey(1, 4)]: "cinema" });
    expect(bootPreset(store, { pathname: "/login" })).toBeNull();
    expect(bootPreset(store, { pathname: "/register" })).toBeNull();
    expect(bootPreset(store, { pathname: "/profiles" })).toBe("cinema");
  });
});

describe("appearance boot script — both channels at once", () => {
  it("applies a palette and a preset from one scan", () => {
    // The real cold-load case: a profile that has chosen both. Neither may
    // shadow the other, and both have to land before the first paint.
    const store = storeFor(6, {
      [themeKey(2, 6)]: "nord",
      [presetKey(2, 6)]: "editorial",
    });
    expect(bootBoth(store)).toEqual({ theme: "nord", preset: "editorial" });
  });

  it("applies whichever half the profile has chosen", () => {
    // Every existing profile is in this state the first time it loads after
    // presets ship: a stored theme and no stored preset.
    expect(bootBoth(storeFor(6, { [themeKey(2, 6)]: "nord" }))).toEqual({
      theme: "nord",
      preset: null,
    });
    expect(bootBoth(storeFor(6, { [presetKey(2, 6)]: "flat" }))).toEqual({
      theme: null,
      preset: "flat",
    });
  });

  it("does not let one profile's preset ride in on another's palette", () => {
    // The channels share a scan but not a match: each one re-checks the
    // profile suffix against its own base.
    const store = storeFor(6, {
      [themeKey(2, 6)]: "nord",
      [presetKey(2, 4)]: "cinema",
    });
    expect(bootBoth(store)).toEqual({ theme: "nord", preset: null });
  });
});
