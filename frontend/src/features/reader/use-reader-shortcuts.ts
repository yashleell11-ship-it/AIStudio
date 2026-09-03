"use client";

import { useShortcut } from "@/lib/keyboard";
import {
  AUTO_SCROLL_SHORTCUT_KEYS,
  CINEMA_SHORTCUT_KEYS,
  SERIES_SHORTCUT_KEYS,
  horizontalTurn,
  horizontalTurnDescription,
  type PageTurn,
} from "./keymap";
import type { ReadingDirection } from "./types";

const GROUP = "Reader";

export interface ReaderShortcutHandlers {
  direction: ReadingDirection;
  onTurnPage: (turn: PageTurn) => void;
  onScrollScreen: (turn: PageTurn) => void;
  onFirstPage: () => void;
  onLastPage: () => void;
  onToggleFullscreen: () => void;
  onToggleCinema: () => void;
  /** Play/pause auto-scroll. A no-op outside continuous mode. */
  onToggleAutoScroll: () => void;
  onEscape: () => void;
  onPreviousChapter: () => void;
  onNextChapter: () => void;
  onOpenSeries: () => void;
  onBookmark: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onZoomReset: () => void;
}

/**
 * Every reader binding, registered against the app-wide keyboard registry — the
 * registry already owns the single keydown listener and refuses to fire while
 * focus is in an input, textarea, select or contenteditable.
 *
 * The horizontal keys carry a direction-derived label so the shortcuts sheet
 * tells the truth in a right-to-left chapter, where left is forward.
 *
 * `?` is deliberately NOT here: the sheet is app-wide and the shell owns that
 * binding (`components/keyboard/ShortcutsDialog`). Registering it twice would
 * put two identical rows in the sheet, and only the first would ever fire.
 */
export function useReaderShortcuts(handlers: ReaderShortcutHandlers): void {
  const { direction } = handlers;

  useShortcut({
    id: "reader.turn-right",
    keys: ["arrowright", "d"],
    description: `${horizontalTurnDescription("right", direction)} (right)`,
    group: GROUP,
    handler: () => handlers.onTurnPage(horizontalTurn("right", direction)),
  });

  useShortcut({
    id: "reader.turn-left",
    keys: ["arrowleft", "a"],
    description: `${horizontalTurnDescription("left", direction)} (left)`,
    group: GROUP,
    handler: () => handlers.onTurnPage(horizontalTurn("left", direction)),
  });

  useShortcut({
    id: "reader.next-page",
    keys: "j",
    description: "Next page",
    group: GROUP,
    handler: () => handlers.onTurnPage("advance"),
  });

  useShortcut({
    id: "reader.previous-page",
    keys: "k",
    description: "Previous page",
    group: GROUP,
    handler: () => handlers.onTurnPage("retreat"),
  });

  useShortcut({
    id: "reader.advance-screen",
    keys: "space",
    description: "Advance one screen",
    group: GROUP,
    handler: () => handlers.onScrollScreen("advance"),
  });

  useShortcut({
    id: "reader.retreat-screen",
    keys: "shift+space",
    description: "Back one screen",
    group: GROUP,
    handler: () => handlers.onScrollScreen("retreat"),
  });

  useShortcut({
    id: "reader.first-page",
    keys: "home",
    description: "First page",
    group: GROUP,
    handler: () => handlers.onFirstPage(),
  });

  useShortcut({
    id: "reader.last-page",
    keys: "end",
    description: "Last page",
    group: GROUP,
    handler: () => handlers.onLastPage(),
  });

  useShortcut({
    id: "reader.fullscreen",
    keys: "f",
    description: "Toggle fullscreen",
    group: GROUP,
    handler: () => handlers.onToggleFullscreen(),
  });

  useShortcut({
    id: "reader.cinema",
    keys: CINEMA_SHORTCUT_KEYS,
    description: "Toggle cinema mode (hide all chrome)",
    group: GROUP,
    handler: () => handlers.onToggleCinema(),
  });

  useShortcut({
    id: "reader.auto-scroll",
    keys: AUTO_SCROLL_SHORTCUT_KEYS,
    description: "Play/pause auto-scroll (continuous mode)",
    group: GROUP,
    handler: () => handlers.onToggleAutoScroll(),
  });

  useShortcut({
    id: "reader.escape",
    keys: "escape",
    description: "Close overlay, leave fullscreen, or exit the reader",
    group: GROUP,
    handler: () => handlers.onEscape(),
  });

  useShortcut({
    id: "reader.prev-chapter",
    keys: "h",
    description: "Previous chapter",
    group: GROUP,
    handler: () => handlers.onPreviousChapter(),
  });

  useShortcut({
    id: "reader.next-chapter",
    keys: "l",
    description: "Next chapter",
    group: GROUP,
    handler: () => handlers.onNextChapter(),
  });

  useShortcut({
    id: "reader.series",
    keys: SERIES_SHORTCUT_KEYS,
    description: "Go to series page",
    group: GROUP,
    handler: () => handlers.onOpenSeries(),
  });

  useShortcut({
    id: "reader.bookmark",
    keys: "b",
    description: "Bookmark current page",
    group: GROUP,
    handler: () => handlers.onBookmark(),
  });

  useShortcut({
    id: "reader.zoom-in",
    keys: ["=", "+", "shift+="],
    description: "Zoom in",
    group: GROUP,
    handler: () => handlers.onZoomIn(),
  });

  useShortcut({
    id: "reader.zoom-out",
    keys: "-",
    description: "Zoom out",
    group: GROUP,
    handler: () => handlers.onZoomOut(),
  });

  useShortcut({
    id: "reader.zoom-reset",
    keys: "0",
    description: "Reset zoom",
    group: GROUP,
    handler: () => handlers.onZoomReset(),
  });
}
