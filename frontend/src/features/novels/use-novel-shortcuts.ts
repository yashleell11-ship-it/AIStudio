"use client";

import { useShortcut } from "@/lib/keyboard";

const GROUP = "Novel reader";

export interface NovelShortcutHandlers {
  onPreviousChapter: () => void;
  onNextChapter: () => void;
  onLargerText: () => void;
  onSmallerText: () => void;
  onToggleTypePanel: () => void;
  /** Capture the exact paragraph being read, in one press. */
  onBookmark: () => void;
  /** False before the chapter's text is on screen: there is no spot to save. */
  canBookmark?: boolean;
  onEscape: () => void;
}

/**
 * The novel reader's bindings.
 *
 * Deliberately a short list, and deliberately the manga reader's own keys where
 * the two readers mean the same thing — `h`/`l` for chapters, `-`/`=` for size,
 * `b` to bookmark, Escape to leave. A reader who moves between the two modes
 * should not have to learn a second keyboard.
 *
 * Only ever mounted inside the novel reader, so these do not collide with the
 * manga reader's identical keys: neither reader is on screen while the other
 * is. Scrolling is the browser's (Space, PageDown, arrows) — a prose column has
 * no page model to override it with, which is exactly why there is no `j`/`k`
 * page-turn pair here.
 *
 * `?` is the shell's, app-wide; registering it again would put a duplicate row
 * in the shortcuts sheet.
 */
export function useNovelShortcuts(handlers: NovelShortcutHandlers): void {
  useShortcut({
    id: "novel.previous-chapter",
    keys: "h",
    description: "Previous chapter",
    group: GROUP,
    handler: () => handlers.onPreviousChapter(),
  });

  useShortcut({
    id: "novel.next-chapter",
    keys: "l",
    description: "Next chapter",
    group: GROUP,
    handler: () => handlers.onNextChapter(),
  });

  useShortcut({
    id: "novel.larger-text",
    keys: ["=", "+", "shift+="],
    description: "Larger text",
    group: GROUP,
    handler: () => handlers.onLargerText(),
  });

  useShortcut({
    id: "novel.smaller-text",
    keys: "-",
    description: "Smaller text",
    group: GROUP,
    handler: () => handlers.onSmallerText(),
  });

  useShortcut({
    id: "novel.type-panel",
    keys: "t",
    description: "Type and page settings",
    group: GROUP,
    handler: () => handlers.onToggleTypePanel(),
  });

  // "B" for bookmark, the manga reader's own key for the same act — the two
  // readers mean the same thing by it, so a reader who moves between them does
  // not have to learn a second keyboard. Registered (and so listed in the `?`
  // sheet) only while there is a paragraph under the reading line to record.
  useShortcut({
    id: "novel.bookmark",
    keys: "b",
    description: "Bookmark this spot",
    group: GROUP,
    enabled: handlers.canBookmark !== false,
    handler: () => handlers.onBookmark(),
  });

  useShortcut({
    id: "novel.exit",
    keys: "escape",
    description: "Back to the book",
    group: GROUP,
    handler: () => handlers.onEscape(),
  });
}
