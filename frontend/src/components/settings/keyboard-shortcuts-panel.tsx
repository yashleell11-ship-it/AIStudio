"use client";

import { Keyboard } from "lucide-react";
import { KbdCombo } from "@/components/ui/kbd";
import {
  formatKeyCombo,
  groupShortcuts,
  shortcutCombos,
  useRegisteredShortcuts,
} from "@/lib/keyboard";
import { cn } from "@/lib/cn";

/**
 * Grouping/ordering lives in `lib/keyboard/groups` and is shared with the `?`
 * cheat-sheet, so the two listings can never disagree about what goes where.
 */
export function KeyboardShortcutsPanel() {
  const shortcuts = useRegisteredShortcuts();
  const groups = groupShortcuts(shortcuts);

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <Keyboard className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Keyboard Shortcuts</h2>
          <p className="mt-0.5 text-sm text-muted">
            Active shortcuts registered across the app. Shortcuts are disabled while typing in
            input fields unless noted.
          </p>
        </div>
      </div>

      {groups.length === 0 ? (
        <p className="text-sm text-muted">No shortcuts registered yet.</p>
      ) : (
        <div className="space-y-6">
          {groups.map((group) => (
            <div key={group.name}>
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
                {group.name}
              </h3>
              <ul className="divide-y divide-border rounded-xl border border-border bg-surface-2/40">
                {group.shortcuts.map((shortcut) => (
                  <li
                    key={shortcut.id}
                    className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-surface-2/40"
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
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
