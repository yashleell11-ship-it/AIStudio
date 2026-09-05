import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import { DESIGN_PRESET_META } from "@/features/preferences/presets";
import {
  activeDesignPreset,
  subscribeDesignPreset,
} from "@/features/preferences/preset-store";

/**
 * How tightly the library grid packs covers.
 *
 * Per (user, profile) rather than device-global, like every other client-side
 * store here: the backend has no reader-layout model, and two personas sharing a
 * browser have different eyesight and different libraries — one of them
 * re-choosing "compact" on every switch is exactly the papercut profiles exist
 * to avoid. It is a display preference, not a disclosure, but a device-global
 * key for per-profile data is the pattern that was just removed from three
 * stores and must not come back in a fourth.
 *
 * This subsumes the old grid/list toggle: `list` IS a density.
 *
 * ### Where the default comes from
 *
 * Not from this module. "Poster grid, list, or compact rows" is one of the
 * things a DESIGN PRESET decides — Compact opens on the dense cover grid,
 * Editorial on the list, everything else on the poster grid — so an unset
 * density resolves through the active preset rather than through a constant
 * here. An explicit choice still wins forever after, exactly as a chosen theme
 * wins over the default palette: the preset seeds, it does not override.
 */

const STORAGE_BASE = "manhwamaniacs:library-density";

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const DENSITY_EVENT = "manhwamaniacs:library-density";

export const LIBRARY_DENSITIES = ["comfortable", "compact", "list"] as const;

export type LibraryDensity = (typeof LIBRARY_DENSITIES)[number];

export const DEFAULT_LIBRARY_DENSITY: LibraryDensity = "comfortable";

export function parseLibraryDensity(
  raw: string | null,
  fallback: LibraryDensity = DEFAULT_LIBRARY_DENSITY,
): LibraryDensity {
  return raw !== null && (LIBRARY_DENSITIES as readonly string[]).includes(raw)
    ? (raw as LibraryDensity)
    : fallback;
}

/** The layout the active design preset opens the library on. */
export function presetLibraryDensity(): LibraryDensity {
  return DESIGN_PRESET_META[activeDesignPreset()].density;
}

/**
 * The active profile's density, or the preset's opening layout when it has
 * never chosen one. With no active profile there is no stored value to read,
 * which lands on the preset's default too.
 */
export function readLibraryDensity(): LibraryDensity {
  return parseLibraryDensity(readScopedString(STORAGE_BASE), presetLibraryDensity());
}

export function writeLibraryDensity(density: LibraryDensity): void {
  if (typeof window === "undefined") {
    return;
  }
  writeScopedString(STORAGE_BASE, density);
  window.dispatchEvent(new Event(DENSITY_EVENT));
}

// `useSyncExternalStore` compares snapshots by reference. A density is a string
// so the reference is stable for free, but the read still has to be cached by
// scoped key + raw value or a profile switch would go unnoticed — and by the
// active preset, since that is what an unset value resolves through.
let snapshot: {
  key: string | null;
  raw: string | null;
  preset: string | null;
  value: LibraryDensity;
} = {
  key: null,
  raw: null,
  preset: null,
  value: DEFAULT_LIBRARY_DENSITY,
};

export function getLibraryDensitySnapshot(): LibraryDensity {
  const key = activeStorageKey(STORAGE_BASE);
  const raw = readScopedString(STORAGE_BASE);
  const preset = activeDesignPreset();
  if (snapshot.key !== key || snapshot.raw !== raw || snapshot.preset !== preset) {
    snapshot = {
      key,
      raw,
      preset,
      value: parseLibraryDensity(raw, DESIGN_PRESET_META[preset].density),
    };
  }
  return snapshot.value;
}

export function getLibraryDensityServerSnapshot(): LibraryDensity {
  return DEFAULT_LIBRARY_DENSITY;
}

export function subscribeLibraryDensity(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  const handler = () => onStoreChange();
  window.addEventListener(DENSITY_EVENT, handler);
  window.addEventListener("storage", handler);
  // A profile switch changes which key this reads without touching localStorage,
  // so no DOM event announces it.
  const unsubscribeScope = subscribeStorageScope(handler);
  // And a preset change moves the default this resolves to, which is the whole
  // of how "changing the design relays out the library" works without a reload.
  const unsubscribePreset = subscribeDesignPreset(handler);
  return () => {
    window.removeEventListener(DENSITY_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
    unsubscribePreset();
  };
}

/**
 * Grid columns per density.
 *
 * The whole point of the control is that a 27" monitor should not render covers
 * at phone size, so `comfortable` grows the cover on wide viewports instead of
 * only adding columns, and `compact` keeps going past the old six-column ceiling.
 * Both stay at two/three columns on a phone, where there is no room to trade.
 */
export function densityGridClassName(density: LibraryDensity): string {
  switch (density) {
    case "compact":
      return "grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 2xl:grid-cols-12";
    case "list":
      return "space-y-3";
    default:
      return "grid grid-cols-2 gap-5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6";
  }
}

/**
 * The `sizes` hint for a cover at this density. Wrong values here cost real
 * bandwidth: this string is now what the cover proxy's `?w=` is derived from
 * (`lib/cover-url.ts`), so it is no longer only a hint the browser may round —
 * it is the width the backend renders to.
 *
 * The phone branch is therefore written as the exact cell, not as a round `vw`.
 * `grid-cols-2 gap-5` inside the view's `px-6` is `calc(50vw - 34px)`, which is
 * 153px on a 375px phone; the old `50vw` claimed 187px, and 187 x DPR 3 lands
 * one rung further up the server's ladder (720 instead of 480) for every cover
 * on the screen. Above `sm` the layout gains columns faster than the viewport
 * grows and a single value cannot track it, so the wide branch is the widest
 * cell the grid reaches — over-asking on a desktop costs one ladder rung on the
 * connection least likely to care, while under-asking would be a blurry grid.
 */
export function densityCoverSizes(density: LibraryDensity): string {
  switch (density) {
    case "compact":
      // `grid-cols-3 gap-3`; widest cell is the 12-up 2xl row inside max-w-110rem.
      return "(max-width: 639px) calc(33.33vw - 24px), 140px";
    case "list":
      return "64px";
    default:
      // `grid-cols-2 gap-5`; widest cell is the 6-up 2xl row inside max-w-110rem.
      return "(max-width: 639px) calc(50vw - 34px), 264px";
  }
}

export const DENSITY_LABELS: Record<LibraryDensity, string> = {
  comfortable: "Comfortable",
  compact: "Compact",
  list: "List",
};
