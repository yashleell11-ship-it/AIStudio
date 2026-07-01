"use client";

import { Keyboard } from "lucide-react";
import { KbdCombo } from "@/components/ui/kbd";
import { formatKeyCombo } from "@/lib/keyboard/format";
import { useRegisteredShortcuts } from "@/lib/keyboard";
import type { Shortcut } from "@/lib/keyboard/types";
import { cn } from "@/lib/cn";

const GROUP_ORDER = ["General", "Library", "Search", "Sources", "Reader"] as const;

function groupShortcuts(shortcuts: Shortcut[]): Map<string, Shortcut[]> {
  const groups = new Map<string, Shortcut[]>();
  for (const shortcut of shortcuts) {
    const group = shortcut.group ?? "General";
    const existing = groups.get(group) ?? [];
    existing.push(shortcut);
    groups.set(group, existing);
  }
  for (const [, items] of groups) {
    items.sort((a, b) => a.description.localeCompare(b.description));
  }
  return groups;
}

function orderedGroups(groups: Map<string, Shortcut[]>): [string, Shortcut[]][] {
  const ordered: [string, Shortcut[]][] = [];
  for (const name of GROUP_ORDER) {
    const items = groups.get(name);
    if (items?.length) {
      ordered.push([name, items]);
      groups.delete(name);
    }
  }
  for (const [name, items] of groups) {
    ordered.push([name, items]);
  }
  return ordered;
}

export function KeyboardShortcutsPanel() {
  const shortcuts = useRegisteredShortcuts();
  const groups = orderedGroups(groupShortcuts(shortcuts));

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500/20 to-cyan-500/10 text-violet-400">
          <Keyboard className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-fg">Keyboard Shortcuts</h2>
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
          {groups.map(([group, items]) => (
            <div key={group}>
              <h3 className="mb-3 text-[11px] font-semibold uppercase tracking-widest text-muted">
                {group}
              </h3>
              <ul className="divide-y divide-border/40 rounded-xl border border-border/40 bg-white/[0.02]">
                {items.map((shortcut) => {
                  const combos = Array.isArray(shortcut.keys) ? shortcut.keys : [shortcut.keys];
                  return (
                    <li
                      key={shortcut.id}
                      className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 transition-colors hover:bg-white/[0.02]"
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
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
