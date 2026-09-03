"use client";

import { useMemo } from "react";
import { Dialog } from "@/components/ui/dialog";
import { Kbd, KbdCombo } from "@/components/ui/kbd";
import {
  formatKeyCombo,
  groupShortcuts,
  shortcutCombos,
  useRegisteredShortcuts,
} from "@/lib/keyboard";
import { cn } from "@/lib/cn";

interface ShortcutsDialogProps {
  open: boolean;
  onClose: () => void;
}

/**
 * The app-wide `?` cheat-sheet.
 *
 * Reads the live keyboard registry rather than a second hand-written list, so
 * it can never drift from what is actually bound — and because the registry is
 * live, the sheet only ever lists what works on the screen the reader is
 * looking at (the Reader group appears inside a chapter and nowhere else, and
 * the left/right labels swap in a right-to-left chapter).
 *
 * Replaces the reader-only overlay this grew out of: the shell owns the binding
 * and the open flag (`ui-store`), so the same sheet answers "what can I press
 * here?" on every screen instead of only inside a chapter.
 */
export function ShortcutsDialog({ open, onClose }: ShortcutsDialogProps) {
  const shortcuts = useRegisteredShortcuts();
  const groups = useMemo(() => groupShortcuts(shortcuts), [shortcuts]);

  if (!open) return null;

  return (
    <Dialog open={open} onClose={onClose} title="Keyboard shortcuts" className="max-w-xl">
      <p className="mb-4 text-sm text-muted">
        Only what works right here is listed. Shortcuts pause while you are typing
        in a field. Press <Kbd>?</Kbd> anywhere to reopen this, <Kbd>Esc</Kbd> to
        close.
      </p>

      {groups.length === 0 ? (
        <p className="text-sm text-muted">No shortcuts are active on this screen.</p>
      ) : (
        <div className="max-h-[60vh] space-y-5 overflow-y-auto">
          {groups.map((group) => (
            <section key={group.name}>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-widest text-muted">
                {group.name}
              </h3>
              <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border bg-surface-2/40">
                {group.shortcuts.map((shortcut) => (
                  <li
                    key={shortcut.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5"
                  >
                    <span className="text-sm text-fg">{shortcut.description}</span>
                    <div className="flex flex-wrap items-center gap-2">
                      {shortcutCombos(shortcut).map((combo, index) => (
                        <KbdCombo
                          key={`${shortcut.id}-${index}`}
                          tokens={formatKeyCombo(combo)}
                          className={cn(index > 0 && "opacity-80")}
                        />
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </Dialog>
  );
}
