import type { KeyCombo, Shortcut } from "./types";

/**
 * Group order for every surface that lists shortcuts (the `?` cheat-sheet and
 * Settings → Keyboard Shortcuts). Roughly "what you can do anywhere" first,
 * then the screen-specific sets, with the reader — by far the largest group —
 * last so it never buries the rest.
 */
export const SHORTCUT_GROUP_ORDER = [
  "General",
  "Navigation",
  "Library",
  "Search",
  "Sources",
  "Reader",
] as const;

/** Where a shortcut with no `group` is filed. */
export const DEFAULT_SHORTCUT_GROUP = "General";

export interface ShortcutGroup {
  name: string;
  shortcuts: Shortcut[];
}

/** A shortcut's combos, normalised to an array for rendering. */
export function shortcutCombos(shortcut: Shortcut): KeyCombo[] {
  return Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];
}

/**
 * Bucket the live registry into display groups.
 *
 * Known groups come out in `SHORTCUT_GROUP_ORDER`; anything else follows
 * alphabetically, so a group added by a future feature lands somewhere stable
 * rather than wherever its component happened to mount. Shortcuts inside a
 * group are sorted by description for the same reason — registration order is
 * a mount-order accident and would reshuffle the sheet as the user navigates.
 */
export function groupShortcuts(shortcuts: readonly Shortcut[]): ShortcutGroup[] {
  const buckets = new Map<string, Shortcut[]>();
  for (const shortcut of shortcuts) {
    const name = shortcut.group ?? DEFAULT_SHORTCUT_GROUP;
    const existing = buckets.get(name);
    if (existing) existing.push(shortcut);
    else buckets.set(name, [shortcut]);
  }
  for (const items of buckets.values()) {
    items.sort((a, b) => a.description.localeCompare(b.description));
  }

  const ordered: ShortcutGroup[] = [];
  for (const name of SHORTCUT_GROUP_ORDER) {
    const items = buckets.get(name);
    if (items?.length) {
      ordered.push({ name, shortcuts: items });
      buckets.delete(name);
    }
  }
  for (const name of Array.from(buckets.keys()).sort()) {
    ordered.push({ name, shortcuts: buckets.get(name) ?? [] });
  }
  return ordered;
}
