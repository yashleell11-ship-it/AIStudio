"use client";

import { BookOpen, BookText } from "lucide-react";
import { cn } from "@/lib/cn";
import { CONTENT_MODE_COPY, CONTENT_MODES, type ContentMode } from "../mode";
import { useContentMode } from "../use-content-mode";

const MODE_ICON = {
  manga: BookOpen,
  novel: BookText,
} as const;

export interface ContentModeSwitchProps {
  /** Icon-only, for the collapsed sidebar rail. */
  collapsed?: boolean;
  className?: string;
}

/**
 * The app-wide Manga / Novels switch.
 *
 * A segmented two-way control at the very top of the sidebar, above the nav
 * groups, because it is a MODE and not a filter: it decides what Library,
 * Sources, Updates, Search and the rest are lists *of*. A chip inside one of
 * those screens would read as "this page is filtered", which is the wrong
 * mental model and would leave the other eleven screens looking unfiltered.
 *
 * **Renders nothing when the server has novels off.** Not disabled, not
 * greyed — absent, so a dark deployment is the manga app it has always been.
 */
export function ContentModeSwitch({ collapsed, className }: ContentModeSwitchProps) {
  const { mode, setMode, novelsEnabled } = useContentMode();

  if (!novelsEnabled) return null;

  return (
    <div
      role="group"
      aria-label="Content mode"
      className={cn(
        "flex gap-1 rounded-xl border border-border bg-surface-2/60 p-1",
        collapsed && "flex-col",
        className,
      )}
    >
      {CONTENT_MODES.map((candidate) => (
        <ModeButton
          key={candidate}
          mode={candidate}
          active={mode === candidate}
          collapsed={collapsed}
          onSelect={setMode}
        />
      ))}
    </div>
  );
}

function ModeButton({
  mode,
  active,
  collapsed,
  onSelect,
}: {
  mode: ContentMode;
  active: boolean;
  collapsed?: boolean;
  onSelect: (mode: ContentMode) => void;
}) {
  const Icon = MODE_ICON[mode];
  const label = CONTENT_MODE_COPY[mode].label;

  return (
    <button
      type="button"
      // `aria-pressed` rather than a radio group: this is two toggle buttons
      // showing which view you are in, and a radiogroup would demand arrow-key
      // navigation semantics the sidebar does not otherwise use.
      aria-pressed={active}
      title={collapsed ? label : undefined}
      onClick={() => onSelect(mode)}
      className={cn(
        "flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-widest transition-colors",
        collapsed && "px-0 tracking-normal",
        active
          ? "bg-primary text-primary-fg shadow-glow"
          : "text-muted hover:bg-surface-2 hover:text-fg",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden />
      {collapsed ? <span className="sr-only">{label}</span> : <span>{label}</span>}
    </button>
  );
}
