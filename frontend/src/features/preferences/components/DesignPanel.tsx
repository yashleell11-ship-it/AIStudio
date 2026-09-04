"use client";

import { useCallback, useEffect, useRef } from "react";
import Link from "next/link";
import { Check, LayoutTemplate } from "lucide-react";
import { PROFILE_PICKER_PATH } from "@/features/profiles/access";
import { useActiveProfileStore } from "@/features/profiles/store";
import { cn } from "@/lib/cn";
import { DESIGN_PRESETS, designPresetList, type DesignPreset } from "../presets";
import { useDesignPreset } from "../preset-store";
import { PresetSwatch } from "./PresetSwatch";

/**
 * The design preset gallery.
 *
 * Themes answer "what colour is this app" next door; this answers "what shape
 * is it". Five tiles, not forty-two, so there is no filter and no grouping —
 * the whole point of a preset is that it is a position somebody took, and five
 * positions fit on a screen.
 *
 * ### Preview by actually applying it
 *
 * Hovering or focusing a tile stamps that preset on `<html>` immediately, so
 * the entire page — this panel included — reshapes under the cursor: surfaces
 * lose their blur, the type steps down, the margins open. Leaving restores the
 * committed choice. Clicking makes it permanent.
 *
 * This is the honest preview. A design preset changes things a thumbnail
 * cannot show (how much fits on a screen, how much the interface moves), and
 * the app is right there. It is also free: everything a preset moves is a CSS
 * custom property, so the swap is a cascade re-resolution with no remount and
 * no request.
 *
 * The transient attribute is written directly rather than through the store on
 * purpose — a preview must not be persisted, must not survive a profile switch,
 * and must not be seen by another tab. `useApplyDesignPreset` in the shell
 * re-asserts the real value on every commit, and `restore()` covers the rest.
 *
 * The choice is stored per (user, profile), and `scoped-storage` drops a write
 * with no scope rather than falling back to a device-global key. So without an
 * active profile the radios are DISABLED rather than merely unsaved: clicking
 * one would write nothing and the selection would spring back. Same shape as
 * the theme gallery and the mature-content toggle.
 */
export function DesignPanel() {
  const { preset, setPreset, isExplicit } = useDesignPreset();
  const hasProfile = useActiveProfileStore((state) => state.activeProfile !== null);

  // The committed value, readable from an event handler without re-binding it
  // on every render — `restore` has to put back whatever is current NOW, which
  // after a click is the preset that was just chosen, not the one this handler
  // closed over.
  const committed = useRef<DesignPreset>(preset);
  useEffect(() => {
    committed.current = preset;
  }, [preset]);

  const preview = useCallback(
    (next: DesignPreset) => {
      if (!hasProfile) return;
      document.documentElement.dataset.preset = next;
    },
    [hasProfile],
  );

  const restore = useCallback(() => {
    if (!hasProfile) return;
    document.documentElement.dataset.preset = committed.current;
  }, [hasProfile]);

  // A tile can be left without a pointerleave — the panel unmounts on a tab
  // change, the route changes under a focused tile — and a preview that
  // outlived its tile would be a look the viewer never chose and cannot undo
  // from here.
  useEffect(() => restore, [restore]);

  return (
    <section className="glass-card rounded-2xl p-5 md:p-6">
      <div className="mb-5 flex items-start gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-primary/20 to-accent/10 text-primary">
          <LayoutTemplate className="size-5" aria-hidden />
        </div>
        <div>
          <h2 className="font-display text-lg tracking-wide text-fg">Design</h2>
          <p className="mt-0.5 text-sm text-muted">
            {isExplicit
              ? `${DESIGN_PRESETS.length} presets. Each one reshapes the whole app — density, surfaces, type, layout. Independent of the palette, and saved for this profile on this device.`
              : `Using the app's own design. Pick one of ${DESIGN_PRESETS.length} presets to reshape density, surfaces, type and layout — the palette is a separate choice and is not touched.`}
          </p>
        </div>
      </div>

      {!hasProfile ? (
        <div className="mb-4 rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-fg">
          <p>
            No reading profile is active. A design is saved against the profile
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
        <legend className="sr-only">Design preset</legend>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {designPresetList().map((meta) => {
            const selected = meta.id === preset;
            return (
              <label
                key={meta.id}
                onPointerEnter={() => preview(meta.id)}
                onPointerLeave={restore}
                className={cn(
                  "group relative flex flex-col gap-2.5 rounded-2xl border p-2.5 transition-colors",
                  hasProfile ? "cursor-pointer" : "cursor-not-allowed opacity-60",
                  selected
                    ? "border-primary/60 bg-primary/10"
                    : "border-border bg-surface-2/40",
                  hasProfile && !selected && "hover:border-primary/30",
                  // The ring follows the radio's focus, since the input itself
                  // is visually hidden inside this label.
                  "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-primary",
                )}
              >
                <input
                  type="radio"
                  name="design-preset"
                  value={meta.id}
                  checked={selected}
                  disabled={!hasProfile}
                  onChange={() => setPreset(meta.id)}
                  // Keyboard users arrow through a radio group, which fires
                  // focus without a pointer ever moving. Previewing on focus is
                  // what makes this the same control for both.
                  onFocus={() => preview(meta.id)}
                  onBlur={restore}
                  className="sr-only"
                />
                <PresetSwatch meta={meta} />
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
                    <span className="mt-1 block text-[11px] text-muted/80">
                      {meta.character}
                    </span>
                  </span>
                  {selected ? (
                    <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden />
                  ) : null}
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <p className="mt-5 text-xs text-muted">
        Applies as you pick it — hover a preset to see the whole app in it. No
        reload, and nothing here interrupts a chapter you are in the middle of.
      </p>
    </section>
  );
}
