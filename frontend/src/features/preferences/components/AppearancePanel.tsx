"use client";

import { Check, Palette } from "lucide-react";
import { PROFILE_PICKER_PATH } from "@/features/profiles/access";
import { useActiveProfileStore } from "@/features/profiles/store";
import { cn } from "@/lib/cn";
import Link from "next/link";
import { READING_THEMES, READING_THEME_META, type ReadingTheme } from "../theme";
import { useReadingTheme } from "../theme-store";

/**
 * A miniature of the theme: page background, a raised surface, a line of text
 * and the accent. Painted from the theme's own hexes rather than from the live
 * custom properties, because it has to show a palette that is not applied.
 */
function ThemeSwatch({ theme }: { theme: ReadingTheme }) {
  const { swatch } = READING_THEME_META[theme];
  return (
    <span
      aria-hidden
      className="flex h-16 w-full items-end gap-1.5 rounded-xl border border-border p-2"
      style={{ backgroundColor: swatch.bg }}
    >
      <span
        className="h-full w-1/2 rounded-lg"
        style={{ backgroundColor: swatch.fg, opacity: 0.14 }}
      />
      <span className="flex h-full flex-1 flex-col justify-end gap-1">
        <span
          className="h-1.5 w-full rounded-full"
          style={{ backgroundColor: swatch.fg, opacity: 0.75 }}
        />
        <span
          className="h-1.5 w-2/3 rounded-full"
          style={{ backgroundColor: swatch.accent }}
        />
      </span>
    </span>
  );
}

/**
 * Reading theme picker.
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

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-6 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <Palette className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Appearance</h2>
          <p className="mt-0.5 text-sm text-muted">
            {isExplicit
              ? "Pick the palette you read in. Saved for this profile on this device."
              : "Following your system appearance. Pick one below to fix it for this profile."}
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

      <fieldset>
        <legend className="sr-only">Reading theme</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {READING_THEMES.map((id) => {
            const meta = READING_THEME_META[id];
            const active = theme === id;
            return (
              <label
                key={id}
                className={cn(
                  "group relative flex flex-col gap-3 rounded-2xl border p-3 transition-colors",
                  hasProfile ? "cursor-pointer" : "cursor-not-allowed opacity-60",
                  active
                    ? "border-primary/60 bg-primary/10"
                    : "border-border bg-surface-2/40",
                  hasProfile && !active && "hover:border-primary/30",
                  // The ring follows the radio's focus, since the input itself
                  // is visually hidden inside this label.
                  "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
                )}
              >
                <input
                  type="radio"
                  name="reading-theme"
                  value={id}
                  checked={active}
                  disabled={!hasProfile}
                  onChange={() => setTheme(id)}
                  className="sr-only"
                />
                <ThemeSwatch theme={id} />
                <span className="flex items-start justify-between gap-2">
                  <span className="min-w-0">
                    <span
                      className={cn(
                        "block text-sm font-medium",
                        active ? "text-primary" : "text-fg",
                      )}
                    >
                      {meta.label}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted">
                      {meta.description}
                    </span>
                  </span>
                  {active ? (
                    <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                  ) : null}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
    </section>
  );
}
