"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";
import { READING_THEME_META } from "@/features/preferences/theme";
// Direct, not via the `@/features/preferences` barrel: that barrel also exports
// the settings panels, and the reader has no business pulling those in.
import { useReadingTheme } from "@/features/preferences/theme-store";
import {
  resolvePalette,
  resolvePaletteChoice,
  type NovelPalette,
  type NovelPaletteChoice,
  type PaletteScheme,
} from "./palettes";
import {
  getNovelSettingsServerSnapshot,
  getNovelSettingsSnapshot,
  subscribeNovelSettings,
  writeNovelSettings,
} from "./settings";

export interface NovelPaletteController {
  /** What is stored (or seeded from the site theme) — what the picker ticks. */
  choice: NovelPaletteChoice;
  /**
   * The surface to paint, or `null` for "Follow site theme" — which means
   * render with the app's own `--mm-*` tokens rather than inline colours.
   */
  palette: NovelPalette | null;
  /** Light or dark, whichever surface is actually in force. */
  scheme: PaletteScheme;
  /** The app's own scheme, for seeding and for the picker's grouping. */
  siteScheme: PaletteScheme;
  /**
   * What the app's own theme is called, for the "Follow site theme" row. With
   * forty-two palettes on the site, "dark" no longer tells the reader which
   * surface that option is about to hand them.
   */
  siteThemeLabel: string;
  setChoice: (choice: NovelPaletteChoice) => void;
}

/**
 * The reading surface: one of the twelve palettes, or the app's own theme.
 *
 * Per profile (`settings.ts`), never per series — the page a novel is read on
 * is a property of the room and the hour, not of the book. The site theme only
 * seeds the first choice; after that an explicit palette survives a theme
 * change, which is the whole reason the palette is independent.
 */
export function useNovelPalette(): NovelPaletteController {
  const settings = useSyncExternalStore(
    subscribeNovelSettings,
    getNovelSettingsSnapshot,
    getNovelSettingsServerSnapshot,
  );
  const { theme } = useReadingTheme();
  const siteTheme = READING_THEME_META[theme];
  const siteScheme = siteTheme.scheme;

  const choice = useMemo(
    () => resolvePaletteChoice(settings.palette, siteScheme),
    [settings.palette, siteScheme],
  );
  const palette = useMemo(() => resolvePalette(choice), [choice]);

  const setChoice = useCallback((next: NovelPaletteChoice) => {
    writeNovelSettings({ palette: next });
  }, []);

  return {
    choice,
    palette,
    scheme: palette?.scheme ?? siteScheme,
    siteScheme,
    siteThemeLabel: siteTheme.label,
    setChoice,
  };
}
