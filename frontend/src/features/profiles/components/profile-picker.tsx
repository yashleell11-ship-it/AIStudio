"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { ApiError } from "@/types/api";
import { useProfiles } from "../hooks";
import { MOOD_BASE, moodPickerBackground, type Mood } from "../mood";
import { useActiveProfileStore } from "../store";
import { MAX_PROFILES, type Profile } from "../types";
import { usePrefersReducedMotion } from "../use-prefers-reduced-motion";
import { ProfileForm } from "./profile-form";
import { ProfileTile, type TilePhase } from "./profile-tile";

/** Entrance keyframes, scoped by name — kept here so no global CSS is touched. */
const PICKER_KEYFRAMES = `
@keyframes mm-profile-in {
  from { opacity: 0; transform: translateY(10px) scale(0.92); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  [data-mm-picker] * { animation: none !important; }
}`;

const SELECT_HOLD_MS = 450;
const LEAVE_FADE_MS = 400;

/**
 * The full-bleed profile picker ("What are you going to read today?"). Runs
 * AFTER auth — it never replaces the remembered login — and is where the shell
 * gate sends a signed-in visitor who has not chosen a profile yet. Selecting a
 * profile commits it to client state and fades into the home route.
 */
export function ProfilePicker() {
  const router = useRouter();
  const { data: profiles, isLoading, isError, error, refetch } = useProfiles();
  const setActiveProfile = useActiveProfileStore((s) => s.setActiveProfile);
  const reducedMotion = usePrefersReducedMotion();

  const [selected, setSelected] = useState<Profile | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => {
      for (const id of timers.current) window.clearTimeout(id);
    },
    [],
  );

  const commit = useCallback(
    (profile: Profile) => {
      setActiveProfile(profile);
      router.push("/");
    },
    [setActiveProfile, router],
  );

  const handleSelect = useCallback(
    (profile: Profile) => {
      if (selected) return; // a selection is already resolving
      setSelected(profile);
      if (reducedMotion) {
        commit(profile);
        return;
      }
      // Let the tile scale + background cross-fade play, then fade the whole
      // screen out and route home.
      timers.current.push(
        window.setTimeout(() => {
          setLeaving(true);
          timers.current.push(
            window.setTimeout(() => commit(profile), LEAVE_FADE_MS),
          );
        }, SELECT_HOLD_MS),
      );
    },
    [selected, reducedMotion, commit],
  );

  const mood: Mood = selected?.mood ?? "default";
  const atCapacity = (profiles?.length ?? 0) >= MAX_PROFILES;
  const busy = Boolean(selected);

  const phaseFor = (profile: Profile): TilePhase => {
    if (!selected) return "idle";
    return selected.id === profile.id ? "selected" : "dimmed";
  };

  return (
    <div
      data-mm-picker
      className="relative flex h-dvh w-full flex-col items-center justify-center overflow-hidden px-6"
      style={{ backgroundColor: MOOD_BASE }}
    >
      <style>{PICKER_KEYFRAMES}</style>

      {/* Mood tint layer — cross-fades in when a profile is selected. */}
      <div
        aria-hidden
        className={cn("pointer-events-none absolute inset-0", !reducedMotion && "transition-opacity duration-500")}
        style={{ background: moodPickerBackground(mood), opacity: selected ? 1 : 0 }}
      />

      <div className="relative z-10 flex w-full max-w-4xl flex-col items-center">
        <h1 className="hero-heading text-center font-display text-3xl tracking-wide sm:text-4xl md:text-5xl">
          What are you going to read today?
        </h1>
        <p className="mt-3 text-center text-sm text-muted">
          Choose a reading profile. Your progress, library, and mood follow the profile you pick.
        </p>

        <div className="mt-12 min-h-[13rem] w-full">
          {isLoading ? (
            <PickerStatus>Loading profiles…</PickerStatus>
          ) : isError ? (
            <div className="flex flex-col items-center gap-4">
              <p className="text-sm text-danger">
                {error instanceof ApiError ? error.message : "Could not load your profiles."}
              </p>
              <Button variant="secondary" onClick={() => refetch()}>
                Try again
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap items-start justify-center gap-4 sm:gap-6">
              {(profiles ?? []).map((profile, index) => (
                <ProfileTile
                  key={profile.id}
                  profile={profile}
                  index={index}
                  phase={phaseFor(profile)}
                  reducedMotion={reducedMotion}
                  disabled={busy}
                  onSelect={handleSelect}
                />
              ))}

              {!atCapacity ? (
                <button
                  type="button"
                  onClick={() => setFormOpen(true)}
                  disabled={busy}
                  aria-label="Add a profile"
                  className={cn(
                    "group flex w-24 shrink-0 flex-col items-center gap-3 rounded-2xl p-2 outline-none sm:w-28",
                    "focus-visible:ring-2 focus-visible:ring-primary/60",
                    !reducedMotion && "transition-all duration-300",
                    selected && "opacity-30",
                    selected && !reducedMotion && "blur-[2px]",
                  )}
                  style={
                    reducedMotion
                      ? undefined
                      : {
                          animation: `mm-profile-in 340ms cubic-bezier(0.215,0.61,0.355,1) both`,
                          animationDelay: `${(profiles?.length ?? 0) * 80}ms`,
                        }
                  }
                >
                  <span className="flex size-28 items-center justify-center rounded-2xl border-2 border-dashed border-border/70 text-muted transition-colors group-hover:border-primary/60 group-hover:text-primary md:size-32">
                    <Plus className="size-10" aria-hidden />
                  </span>
                  <span className="text-sm font-medium text-muted group-hover:text-fg">
                    Add profile
                  </span>
                </button>
              ) : null}
            </div>
          )}
        </div>

        {!isLoading && !isError && (profiles?.length ?? 0) === 0 ? (
          <p className="mt-8 text-center text-sm text-muted">
            You don&apos;t have any profiles yet. Create your first one to start reading.
          </p>
        ) : null}
      </div>

      {/* Full-screen mood fill used when routing into home after a selection —
          fixed to the viewport and above everything so the chosen mood colour
          takes over the entire screen, then cross-fades into the app. */}
      <div
        aria-hidden
        className={cn(
          "pointer-events-none fixed inset-0 z-50 h-dvh w-dvw",
          !reducedMotion && "transition-opacity",
        )}
        style={{
          background: moodPickerBackground(mood),
          backgroundColor: MOOD_BASE,
          opacity: leaving ? 1 : 0,
          transitionDuration: `${LEAVE_FADE_MS}ms`,
        }}
      />

      {formOpen ? <ProfileForm onClose={() => setFormOpen(false)} /> : null}
    </div>
  );
}

function PickerStatus({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-center">
      <p className="text-sm text-muted">{children}</p>
    </div>
  );
}
