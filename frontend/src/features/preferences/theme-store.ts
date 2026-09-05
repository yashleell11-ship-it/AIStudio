"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import {
  activeStorageKey,
  readScopedString,
  subscribeStorageScope,
  writeScopedString,
} from "@/lib/scoped-storage";
import {
  DEFAULT_READING_THEME,
  READING_THEME_STORAGE_BASE,
  READING_THEME_META,
  initialReadingTheme,
  parseReadingTheme,
  type ReadingTheme,
} from "./theme";

/**
 * The active profile's reading theme.
 *
 * Per (user, profile) via `@/lib/scoped-storage`, like every other client-side
 * preference: two people sharing a browser have different eyes and different
 * rooms, and a device-global key would hand whoever opens the app next the
 * previous profile's palette. It is also the visible kind of leak — the wrong
 * theme is the first thing you notice on a shared screen.
 *
 * Not a server preference: `PUT /settings` carries the instance-wide content
 * flags, and there is no theme field on it. Inventing one is not this change's
 * job, and a display choice is legitimately per-device anyway.
 */
const READING_THEME_BASE = READING_THEME_STORAGE_BASE;

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const READING_THEME_EVENT = "manhwamaniacs:reading-theme";

/** The stored choice for the active profile, or `null` when there is none. */
export function readStoredReadingTheme(): ReadingTheme | null {
  return parseReadingTheme(readScopedString(READING_THEME_BASE));
}

export function writeReadingTheme(theme: ReadingTheme): void {
  if (typeof window === "undefined") return;
  writeScopedString(READING_THEME_BASE, theme);
  window.dispatchEvent(new Event(READING_THEME_EVENT));
}

// `useSyncExternalStore` compares snapshots by reference; a `ReadingTheme` is a
// string, so the identity check is free and no snapshot cache is needed here
// (unlike the list-shaped scoped stores).
function getSnapshot(): ReadingTheme {
  return initialReadingTheme(readScopedString(READING_THEME_BASE));
}

function getServerSnapshot(): ReadingTheme {
  // No storage on the server, and nothing else feeds the resolution — the
  // default is what an unset preference means on the client too, so this cannot
  // produce a mismatch the viewer sees.
  return DEFAULT_READING_THEME;
}

function subscribe(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => onStoreChange();
  window.addEventListener(READING_THEME_EVENT, handler);
  window.addEventListener("storage", handler);
  // A profile switch changes which key this reads without touching storage, so
  // no DOM event announces it.
  const unsubscribeScope = subscribeStorageScope(handler);
  return () => {
    window.removeEventListener(READING_THEME_EVENT, handler);
    window.removeEventListener("storage", handler);
    unsubscribeScope();
  };
}

export interface ReadingThemeState {
  theme: ReadingTheme;
  setTheme: (theme: ReadingTheme) => void;
  /**
   * False while the theme is only the default — no choice has been stored for
   * this profile yet, or there is no profile to store one against. The panel
   * says so rather than showing a selection the viewer never made as if they
   * had.
   */
  isExplicit: boolean;
}

/** Whether a choice is actually stored, as opposed to being the default. */
function getExplicitSnapshot(): boolean {
  return hasStorageScope() && readStoredReadingTheme() !== null;
}

/**
 * Whether the (user, profile) scope this preference is keyed by exists yet.
 *
 * It does not, for a beat, on every cold load of an authenticated page: the
 * scope is published only once the session probe answers and the persisted
 * profile has rehydrated. Until then this store cannot tell "no theme stored"
 * from "not asked yet", and it must not act as though it can — see
 * {@link useApplyReadingTheme}.
 */
function hasStorageScope(): boolean {
  return activeStorageKey(READING_THEME_BASE) !== null;
}

/** Read and write the active profile's reading theme. */
export function useReadingTheme(): ReadingThemeState {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const isExplicit = useSyncExternalStore(subscribe, getExplicitSnapshot, () => false);
  const setTheme = useCallback((next: ReadingTheme) => writeReadingTheme(next), []);
  return { theme, setTheme, isExplicit };
}

/**
 * Publish the active theme as `<html data-theme="…">` — the single attribute
 * every palette keys off, in globals.css and themes.generated.css alike.
 *
 * Written from an effect, never rendered into the markup: the stored value is
 * per (user, profile) and the scope only exists once the session and the
 * profile selection have resolved on the client, so there is nothing the server
 * could have serialised. What covers the gap before hydration is the inline
 * boot script (`appearance-boot.tsx`), which sets the same attribute from the same
 * key before the first paint; this effect then owns it for the rest of the
 * session — profile switches, changes made in another tab, and the picker.
 *
 * Mounted once, by the app shell, which passes `honourBootTheme: false` on the
 * screens that belong to nobody yet (see below).
 */
export function useApplyReadingTheme(honourBootTheme = true): ReadingTheme {
  const { theme } = useReadingTheme();
  const scoped = useSyncExternalStore(subscribe, hasStorageScope, () => false);

  useEffect(() => {
    const root = document.documentElement;
    /*
     * The one case where this must keep its hands off: the scope has not
     * resolved yet, and the boot script already painted something. Between
     * hydration and the session probe answering, `theme` here is only the
     * default — so writing it would repaint a correctly-themed page to GitHub
     * Dark and back a moment later, which is the exact flash the boot script
     * exists to remove, just moved a few hundred milliseconds later.
     *
     * With no attribute present there is nothing to protect (the boot script
     * declines on the auth screens, and finds nothing for a profile that has
     * never chosen), so the default is written as before.
     *
     * `honourBootTheme` is how the shell says the wait is over: on the auth
     * screens the scope will NEVER resolve, so a boot value carried in by a
     * client-side redirect would otherwise sit there forever, showing the last
     * profile's palette to whoever is looking at the login form.
     */
    if (honourBootTheme && !scoped && root.dataset.theme) return;

    root.dataset.theme = theme;
    // The installed-PWA window paints its title bar and the pull-to-refresh
    // gutter from this tag, not from the stylesheet. Left alone it would keep
    // the static GitHub Dark canvas declared in `layout.tsx`, so a Catppuccin
    // Latte install would read as a light app in a black frame.
    const meta = document.querySelector('meta[name="theme-color"]');
    meta?.setAttribute("content", READING_THEME_META[theme].swatch.bg);
  }, [theme, scoped, honourBootTheme]);

  return theme;
}
