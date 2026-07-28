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
const READING_THEME_BASE = "manhwamaniacs:reading-theme";

/** Same-tab notification; `storage` only fires in the tabs that did not write. */
const READING_THEME_EVENT = "manhwamaniacs:reading-theme";

/**
 * Whether the viewer's OS asks for a light UI. Read at snapshot time rather
 * than cached, so the *first* resolution on a machine that prefers light picks
 * light even if the module was imported before the media query was readable.
 */
function prefersLight(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: light)").matches;
}

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
  return initialReadingTheme(readScopedString(READING_THEME_BASE), prefersLight());
}

function getServerSnapshot(): ReadingTheme {
  // No storage and no media query on the server. The CSS `prefers-color-scheme`
  // fallback in globals.css covers the light case for that first paint, so
  // rendering the default here cannot produce a mismatch the viewer sees.
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
  const media = window.matchMedia?.("(prefers-color-scheme: light)");
  // Only matters while nothing is stored — `initialReadingTheme` ignores the
  // query once there is a choice — but without this the very first visit would
  // not follow the OS flipping to dark mode until the next reload.
  media?.addEventListener("change", handler);
  return () => {
    window.removeEventListener(READING_THEME_EVENT, handler);
    window.removeEventListener("storage", handler);
    media?.removeEventListener("change", handler);
    unsubscribeScope();
  };
}

export interface ReadingThemeState {
  theme: ReadingTheme;
  setTheme: (theme: ReadingTheme) => void;
  /**
   * False while the theme is only being inferred from the OS preference — no
   * choice has been stored for this profile yet, or there is no profile to
   * store one against. The panel says so rather than showing a selection the
   * viewer never made as if they had.
   */
  isExplicit: boolean;
}

/** Whether a choice is actually stored, as opposed to inferred from the OS. */
function getExplicitSnapshot(): boolean {
  return (
    activeStorageKey(READING_THEME_BASE) !== null && readStoredReadingTheme() !== null
  );
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
 * every palette in globals.css keys off.
 *
 * Written from an effect, never rendered into the markup: the stored value is
 * per (user, profile) and the scope only exists once the session and the
 * profile selection have resolved on the client, so there is nothing the server
 * could have serialised. The attribute is therefore absent for the first paint,
 * which globals.css handles with its `:root:not([data-theme])` block.
 *
 * Mounted once, by the app shell.
 */
export function useApplyReadingTheme(): ReadingTheme {
  const { theme } = useReadingTheme();

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return theme;
}
