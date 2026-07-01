"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { isEditableTarget, matchesCombo } from "./match";
import type { Shortcut } from "./types";

interface KeyboardRegistry {
  register: (shortcut: Shortcut) => () => void;
  /** Snapshot of registered shortcuts, for a help overlay. */
  shortcuts: Shortcut[];
}

const KeyboardContext = createContext<KeyboardRegistry | null>(null);

/**
 * Owns a single global keydown listener and dispatches to registered shortcuts.
 * One listener for the whole app keeps handling cheap and predictable.
 */
export function KeyboardProvider({ children }: { children: React.ReactNode }) {
  const registry = useRef(new Map<string, Shortcut>());
  const [shortcuts, setShortcuts] = useState<Shortcut[]>([]);

  const sync = useCallback(() => {
    setShortcuts(Array.from(registry.current.values()));
  }, []);

  const register = useCallback(
    (shortcut: Shortcut) => {
      registry.current.set(shortcut.id, shortcut);
      sync();
      return () => {
        registry.current.delete(shortcut.id);
        sync();
      };
    },
    [sync],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const editable = isEditableTarget(event.target);
      for (const shortcut of registry.current.values()) {
        if (editable && !shortcut.allowInInput) continue;
        const combos = Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];
        if (combos.some((combo) => matchesCombo(event, combo))) {
          if (shortcut.preventDefault !== false) event.preventDefault();
          shortcut.handler(event);
          return;
        }
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const value = useMemo<KeyboardRegistry>(
    () => ({ register, shortcuts }),
    [register, shortcuts],
  );

  return (
    <KeyboardContext.Provider value={value}>{children}</KeyboardContext.Provider>
  );
}

function useKeyboardRegistry(): KeyboardRegistry {
  const ctx = useContext(KeyboardContext);
  if (!ctx) {
    throw new Error("Keyboard hooks must be used within <KeyboardProvider>.");
  }
  return ctx;
}

/** Register one shortcut for the lifetime of the calling component. */
export function useShortcut(shortcut: Shortcut): void {
  const { register } = useKeyboardRegistry();
  const handlerRef = useRef(shortcut.handler);

  useEffect(() => {
    handlerRef.current = shortcut.handler;
  }, [shortcut]);

  const { id, description, group, allowInInput, preventDefault } = shortcut;
  const keys = Array.isArray(shortcut.keys) ? shortcut.keys.join("|") : shortcut.keys;

  useEffect(() => {
    return register({
      id,
      description,
      group,
      allowInInput,
      preventDefault,
      keys: keys.includes("|") ? keys.split("|") : keys,
      handler: (event) => handlerRef.current(event),
    });
  }, [register, id, description, group, allowInInput, preventDefault, keys]);
}

/** Read all registered shortcuts (e.g. to render a help overlay). */
export function useRegisteredShortcuts(): Shortcut[] {
  return useKeyboardRegistry().shortcuts;
}
