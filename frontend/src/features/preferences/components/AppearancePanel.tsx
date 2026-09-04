"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Check, Palette, Search, X } from "lucide-react";
import { PROFILE_PICKER_PATH } from "@/features/profiles/access";
import { useActiveProfileStore } from "@/features/profiles/store";
import { cn } from "@/lib/cn";
import {
  READING_THEMES,
  themeMatches,
  themesByScheme,
  type ReadingTheme,
  type ReadingThemeMeta,
} from "../theme";
import type { ThemeScheme } from "../theme-types";
import { useReadingTheme } from "../theme-store";
import { ThemeSwatch } from "./ThemeSwatch";

interface GroupProps {
  scheme: ThemeScheme;
  themes: readonly ReadingThemeMeta[];
  active: ReadingTheme;
  enabled: boolean;
  onPick: (theme: ReadingTheme) => void;
}

const GROUP_TITLE: Record<ThemeScheme, string> = {
  dark: "Dark",
  light: "Light",
};

function ThemeGroup({ scheme, themes, active, enabled, onPick }: GroupProps) {
  if (themes.length === 0) return null;
  return (
    <div>
      <h3 className="mb-3 flex items-baseline gap-2 text-sm font-medium text-fg">
        {GROUP_TITLE[scheme]}
        <span className="text-xs font-normal text-muted">{themes.length}</span>
      </h3>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        {themes.map((meta) => {
          const selected = meta.id === active;
          return (
            <label
              key={meta.id}
              className={cn(
                "group relative flex flex-col gap-2.5 rounded-2xl border p-2.5 transition-colors",
                enabled ? "cursor-pointer" : "cursor-not-allowed opacity-60",
                selected
                  ? "border-primary/60 bg-primary/10"
                  : "border-border bg-surface-2/40",
                enabled && !selected && "hover:border-primary/30",
                // The ring follows the radio's focus, since the input itself is
                // visually hidden inside this label.
                "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
              )}
            >
              <input
                type="radio"
                name="site-theme"
                value={meta.id}
                checked={selected}
                disabled={!enabled}
                onChange={() => onPick(meta.id)}
                className="sr-only"
              />
              <ThemeSwatch swatch={meta.swatch} />
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span
                    className={cn(
                      "block truncate text-sm font-medium",
                      selected ? "text-primary" : "text-fg",
                    )}
                  >
                    {meta.label}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">
                    {meta.description}
                  </span>
                  {meta.author ? (
                    // Community schemes are somebody's work; the tile says whose.
                    <span className="mt-1 block truncate text-[11px] text-muted/80">
                      {meta.author}
                    </span>
                  ) : null}
                </span>
                {selected ? (
                  <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

/**
 * The theme gallery.
 *
 * Four palettes fitted in a flat grid. Forty-two do not, so this adds the two
 * affordances that scale: grouping by dark/light — which is the first question
 * anyone actually has — and a filter, because the fastest way to reach Gruvbox
 * is to type "gruv". The filter matches the name, the blurb and the author, so
 * "paper", "ibm" and "catppuccin" all land somewhere.
 *
 * The choice is stored per (user, profile), and `scoped-storage` drops a write
 * with no scope rather than falling back to a device-global key. So without an
 * active profile the radios are DISABLED rather than merely unsaved: clicking
 * one would write nothing, the store would re-read the OS preference, and the
 * selection would spring back — a control that visibly ignores you is worse
 * than one that explains why it is off. Same shape as the mature-content
 * toggle's `blockReason`.
 */
export function AppearancePanel() {
  const { theme, setTheme, isExplicit } = useReadingTheme();
  const hasProfile = useActiveProfileStore((state) => state.activeProfile !== null);
  const [query, setQuery] = useState("");

  const matches = useMemo(() => {
    const dark = themesByScheme("dark").filter((meta) => themeMatches(meta, query));
    const light = themesByScheme("light").filter((meta) => themeMatches(meta, query));
    return { dark, light, total: dark.length + light.length };
  }, [query]);

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <Palette className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Appearance</h2>
          <p className="mt-0.5 text-sm text-muted">
            {isExplicit
              ? `${READING_THEMES.length} palettes. Each one recolours the whole app. Saved for this profile on this device.`
              : `Following your system appearance. Pick one of ${READING_THEMES.length} palettes to fix it for this profile.`}
          </p>
        </div>
      </div>

      {!hasProfile ? (
        <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-fg">
          <p>
            No reading profile is active. A theme is saved against the profile
            reading it, so there is nowhere to put this choice yet.
          </p>
          <Link
            href={PROFILE_PICKER_PATH}
            className="mt-1 inline-block text-primary hover:underline"
          >
            Choose a profile
          </Link>
        </div>
      ) : null}

      <div className="relative mb-5">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted"
          aria-hidden
        />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Filter palettes — name, author, mood"
          aria-label="Filter palettes"
          className="w-full rounded-xl border border-border bg-surface-2/40 py-2 pl-9 pr-9 text-sm text-fg placeholder:text-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        />
        {query ? (
          <button
            type="button"
            onClick={() => setQuery("")}
            aria-label="Clear filter"
            className="absolute right-2 top-1/2 flex size-6 -translate-y-1/2 items-center justify-center rounded-lg text-muted transition-colors hover:text-fg"
          >
            <X className="size-4" aria-hidden />
          </button>
        ) : null}
      </div>

      <fieldset>
        <legend className="sr-only">Site theme</legend>
        {matches.total === 0 ? (
          <p className="rounded-xl border border-dashed border-border/60 p-6 text-center text-sm text-muted">
            No palette matches “{query.trim()}”.
          </p>
        ) : (
          <div className="space-y-6">
            {(["dark", "light"] as const).map((scheme) => (
              <ThemeGroup
                key={scheme}
                scheme={scheme}
                themes={matches[scheme]}
                active={theme}
                enabled={hasProfile}
                onPick={setTheme}
              />
            ))}
          </div>
        )}
      </fieldset>
    </section>
  );
}
