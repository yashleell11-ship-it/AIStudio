"use client";

import { useMemo } from "react";
import { Dialog } from "@/components/ui/dialog";
import { KbdCombo } from "@/components/ui/kbd";
import { useRegisteredShortcuts } from "@/lib/keyboard";
import { formatKeyCombo } from "@/lib/keyboard/format";
import { cn } from "@/lib/cn";

interface ShortcutsOverlayProps {
  open: boolean;
  onClose: () => void;
}

/**
 * The `?` overlay. Reads the live keyboard registry rather than a second
 * hand-written list, so it can never drift from what the reader actually binds
 * — including the left/right labels, which swap in a right-to-left chapter.
 */
export function ShortcutsOverlay({ open, onClose }: ShortcutsOverlayProps) {
  const shortcuts = useRegisteredShortcuts();

  const readerShortcuts = useMemo(
    () =>
      shortcuts
        .filter((shortcut) => shortcut.group === "Reader")
        .sort((a, b) => a.description.localeCompare(b.description)),
    [shortcuts],
  );

  if (!open) return null;

  return (
    <Dialog open={open} onClose={onClose} title="Reader shortcuts" className="max-w-xl">
      <p className="mb-4 text-sm text-muted">
        Shortcuts pause while you are typing in a field. Press{" "}
        <span className="font-mono text-primary">Esc</span> to close.
      </p>
      <ul className="max-h-[60vh] divide-y divide-border overflow-y-auto rounded-xl border border-border bg-surface-2/40">
        {readerShortcuts.map((shortcut) => {
          const combos = Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];
          return (
            <li
              key={shortcut.id}
              className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5"
            >
              <span className="text-sm text-fg">{shortcut.description}</span>
              <div className="flex flex-wrap items-center gap-2">
                {combos.map((combo, index) => (
                  <KbdCombo
                    key={`${shortcut.id}-${index}`}
                    tokens={formatKeyCombo(combo)}
                    className={cn(index > 0 && "opacity-80")}
                  />
                ))}
              </div>
            </li>
          );
        })}
      </ul>
    </Dialog>
  );
}
