/**
 * Keyboard shortcut contracts. Shortcuts are declared once and registered
 * from any component via the `useShortcut` hook.
 */

/**
 * A key combination string. Segments joined by "+".
 * Use `mod` for the platform-primary modifier (Ctrl on Windows/Linux, Cmd on macOS).
 * Examples: "mod+k", "shift+/", "g l", "escape".
 * A space separates a multi-key sequence (chord).
 */
export type KeyCombo = string;

export interface ShortcutDefinition {
  /** Stable unique id, used for de-duping and the shortcuts help overlay. */
  id: string;
  /** One or more combos that trigger this shortcut. */
  keys: KeyCombo | KeyCombo[];
  /** Human-readable label for the help overlay. */
  description: string;
  /** Logical grouping for the help overlay (e.g. "Navigation"). */
  group?: string;
  /** When false, the shortcut still fires while typing in inputs. Default false. */
  allowInInput?: boolean;
  /**
   * When false the binding is not registered at all, so it neither fires nor
   * appears in the `?` sheet. For a shortcut whose target only exists some of
   * the time (a grid that is currently showing skeletons or an empty state) —
   * hooks cannot be called conditionally, but a registration can.
   */
  enabled?: boolean;
  /** Prevent the browser default when matched. Default true. */
  preventDefault?: boolean;
}

export interface Shortcut extends ShortcutDefinition {
  handler: (event: KeyboardEvent) => void;
}
