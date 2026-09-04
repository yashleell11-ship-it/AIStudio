"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import {
  DEFAULT_DESIGN_PRESET,
  DESIGN_PRESET_META,
  DESIGN_PRESET_STORAGE_BASE,
  initialDesignPreset,
  parseDesignPreset,
  type DesignPreset,
} from "./presets";

/**
 * The active profile's design preset.
 *
 * Per (user, profile) via `@/lib/scoped-storage`, exactly like the reading
 * theme: two people sharing a browser want different things from the same
 * screen, and one of them re-choosing Compact on every switch is the papercut
 * profiles exist to remove.
 *
 * Not a server preference. `PUT /settings` carries the instance-wide content
 * flags and has no appearance field; a display choice is legitimately
 * per-device anyway (the phone in your hand and the 27" monitor want different
 * densities from the same account).
 *
 * ### Applied live, never behind a restart
 *
 * Everything a preset moves is a CSS custom property, so writing the attribute
 * re-resolves the cascade and the page reflows in place — no remount, no lost
 * scroll position, no interrupted chapter. The two decisions that are NOT
 * custom properties (the library's opening layout, whether the reader starts
 * with its chrome hidden) are read through this store by the components that
 * own them, so they re-render on the same change. Nothing here needs a reload,
 * and nothing here should ever ask for one.
 */
const PRESET_BASE = DESIGN_PRESET_STORAGE_BASE;

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const PRESET_EVENT = "manhwamaniacs:design-preset";

/** The stored choice for the active profile, or `null` when there is none. */
export function readStoredDesignPreset(): DesignPreset | null {
  return parseDesignPreset(readScopedString(PRESET_BASE));
}

export function writeDesignPreset(preset: DesignPreset): void {
  if (typeof window === "undefined") return;
  writeScopedString(PRESET_BASE, preset);
  window.dispatchEvent(new Event(PRESET_EVENT));
}

/**
 * The preset in force right now, readable outside React.
 *
 * The stores that carry a preset-derived DEFAULT — the library's density, the
 * reader's chrome — are `useSyncExternalStore` sources of their own and have to
 * resolve their snapshot synchronously, without a hook. This is how they ask.
 *
 * `useSyncExternalStore` compares snapshots by reference; a `DesignPreset` is a
 * string, so the identity check is free and no snapshot cache is needed here
 * (unlike the object-shaped scoped stores).
 */
export function activeDesignPreset(): DesignPreset {
  return initialDesignPreset(readScopedString(PRESET_BASE));
}

function getServerSnapshot(): DesignPreset {
  // No storage on the server. The bare `:root` shape defaults in globals.css
  // ARE the default preset, so rendering it here cannot produce a mismatch the
  // viewer sees.
  return DEFAULT_DESIGN_PRESET;
}

/**
 * Subscribe to every way the active preset can change: this tab, another tab,
 * and a profile switch — which changes the key under the caller's feet without
 * touching localStorage, so nothing else would announce it.
 *
 * Exported because the density and reader-chrome stores chain onto it: their
 * value depends on this one, so their subscribers have to hear about it.
 */
export function subscribeDesignPreset(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => onStoreChange();
  window.addEventListener(PRESET_EVENT, handler);
  window.addEventListener("storage", handler);
  const unsubscribeScope = subscribeStorageScope(handler);
  return () => {
    window.removeEventListener(PRESET_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
  };
}

export interface DesignPresetState {
  preset: DesignPreset;
  setPreset: (preset: DesignPreset) => void;
  /**
   * False while the preset is only the default — no choice has been stored for
   * this profile yet, or there is no profile to store one against. The panel
   * says so rather than showing a selection the viewer never made as if they
   * had.
   */
  isExplicit: boolean;
}

/** Whether the (user, profile) scope this preference is keyed by exists yet. */
function hasStorageScope(): boolean {
  return activeStorageKey(PRESET_BASE) !== null;
}

function getExplicitSnapshot(): boolean {
  return hasStorageScope() && readStoredDesignPreset() !== null;
}

/** Read and write the active profile's design preset. */
export function useDesignPreset(): DesignPresetState {
  const preset = useSyncExternalStore(
    subscribeDesignPreset,
    activeDesignPreset,
    getServerSnapshot,
  );
  const isExplicit = useSyncExternalStore(
    subscribeDesignPreset,
    getExplicitSnapshot,
    () => false,
  );
  const setPreset = useCallback((next: DesignPreset) => writeDesignPreset(next), []);
  return { preset, setPreset, isExplicit };
}

/** The metadata for the preset in force — layout default, motion, character. */
export function useActivePresetMeta() {
  const { preset } = useDesignPreset();
  return DESIGN_PRESET_META[preset];
}

/**
 * How much the JS-driven motion primitives should move, 0 to 1.
 *
 * The CSS half of this is `--shape-motion`, which the app's own keyframes
 * multiply their durations by. Framer-motion animates through React state and
 * cannot read a custom property, so it reads the same number from here.
 */
export function usePresetMotion(): number {
  return useActivePresetMeta().motion;
}

/**
 * Publish the active preset as `<html data-preset="…">` — the single attribute
 * every shape bundle in `presets.css` keys off.
 *
 * Written from an effect, never rendered into the markup, for the same reason
 * the theme is: the stored value is per (user, profile) and that scope only
 * exists once the session and the profile selection have resolved on the
 * client, so there is nothing the server could have serialised. What covers the
 * gap before hydration is the inline boot script
 * (`appearance-boot-source.ts`), which sets the same attribute from the same
 * key before the first paint; this effect then owns it for the rest of the
 * session — profile switches, changes made in another tab, and the picker.
 *
 * Mounted once, by the app shell, which passes `honourBootPreset: false` on the
 * screens that belong to nobody yet.
 */
export function useApplyDesignPreset(honourBootPreset = true): DesignPreset {
  const { preset } = useDesignPreset();
  const scoped = useSyncExternalStore(subscribeDesignPreset, hasStorageScope, () => false);

  useEffect(() => {
    const root = document.documentElement;
    /*
     * The one case where this must keep its hands off: the scope has not
     * resolved yet, and the boot script already applied something. Between
     * hydration and the session probe answering, `preset` here is only the
     * default — so writing it would reflow a correctly-shaped page to Signature
     * and back a moment later, which is the exact jump the boot script exists
     * to remove, just moved a few hundred milliseconds later.
     *
     * With no attribute present there is nothing to protect (the boot script
     * declines on the auth screens, and finds nothing for a profile that has
     * never chosen), so the default is written as before.
     */
    if (honourBootPreset && !scoped && root.dataset.preset) return;

    root.dataset.preset = preset;
  }, [preset, scoped, honourBootPreset]);

  return preset;
}
