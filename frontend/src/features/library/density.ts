import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";

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
 */

const STORAGE_BASE = "manhwamaniacs:library-density";

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const DENSITY_EVENT = "manhwamaniacs:library-density";

export const LIBRARY_DENSITIES = ["comfortable", "compact", "list"] as const;

export type LibraryDensity = (typeof LIBRARY_DENSITIES)[number];

export const DEFAULT_LIBRARY_DENSITY: LibraryDensity = "comfortable";

export function parseLibraryDensity(raw: string | null): LibraryDensity {
  return raw !== null && (LIBRARY_DENSITIES as readonly string[]).includes(raw)
    ? (raw as LibraryDensity)
    : DEFAULT_LIBRARY_DENSITY;
}

/** The default with no active profile — there is no unscoped value to fall back to. */
export function readLibraryDensity(): LibraryDensity {
  return parseLibraryDensity(readScopedString(STORAGE_BASE));
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
// scoped key + raw value or a profile switch would go unnoticed.
let snapshot: { key: string | null; raw: string | null; value: LibraryDensity } = {
  key: null,
  raw: null,
  value: DEFAULT_LIBRARY_DENSITY,
};

export function getLibraryDensitySnapshot(): LibraryDensity {
  const key = activeStorageKey(STORAGE_BASE);
  const raw = readScopedString(STORAGE_BASE);
  if (snapshot.key !== key || snapshot.raw !== raw) {
    snapshot = { key, raw, value: parseLibraryDensity(raw) };
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
  return () => {
    window.removeEventListener(DENSITY_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
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
 * bandwidth on a NAS: a 12-column compact grid asking for full-width images
 * would fetch roughly six times the pixels it can show.
 */
export function densityCoverSizes(density: LibraryDensity): string {
  switch (density) {
    case "compact":
      return "(max-width: 640px) 33vw, (max-width: 1280px) 16vw, 8vw";
    case "list":
      return "64px";
    default:
      return "(max-width: 640px) 50vw, (max-width: 1280px) 25vw, 16vw";
  }
}

export const DENSITY_LABELS: Record<LibraryDensity, string> = {
  comfortable: "Comfortable",
  compact: "Compact",
  list: "List",
};
