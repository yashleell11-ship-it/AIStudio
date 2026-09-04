import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ACTIVE_PROFILE_STORAGE_KEY } from "./storage-key";
import type { ActiveProfile, Profile } from "./types";

/**
 * Which reading profile is currently active. This is CLIENT state (a per-device
 * selection), not server data, so it lives in zustand + localStorage rather than
 * TanStack Query. The selection gates the app: an authenticated visitor with no
 * active profile is routed to the picker (see `access.ts` + the shell gate).
 *
 * `hasHydrated` tells the gate whether the persisted value has been read back
 * yet; the gate must wait for it so a page load never redirects to the picker
 * before the remembered selection is restored.
 *
 * X-Profile-Id: the active id is exposed via {@link getActiveProfileId} so the
 * HTTP layer can attach it as an `X-Profile-Id` header. That header is wired in
 * the shared `services/http` client (owned elsewhere); until then the selection
 * lives here and is read on demand.
 */
interface ActiveProfileState {
  activeProfile: ActiveProfile | null;
  hasHydrated: boolean;
  setActiveProfile: (profile: Profile | ActiveProfile) => void;
  clearActiveProfile: () => void;
  /** Keep the snapshot in sync when the active profile is edited/removed. */
  syncActiveProfile: (profile: Profile) => void;
  setHasHydrated: (value: boolean) => void;
}

/** Reduce a full profile (or an existing snapshot) to the stored snapshot. */
function toSnapshot(profile: Profile | ActiveProfile): ActiveProfile {
  return {
    id: profile.id,
    name: profile.name,
    avatar_key: profile.avatar_key,
    mood: profile.mood,
  };
}

export const useActiveProfileStore = create<ActiveProfileState>()(
  persist(
    (set, get) => ({
      activeProfile: null,
      hasHydrated: false,
      setActiveProfile: (profile) => set({ activeProfile: toSnapshot(profile) }),
      clearActiveProfile: () => set({ activeProfile: null }),
      syncActiveProfile: (profile) => {
        const current = get().activeProfile;
        if (current && current.id === profile.id) {
          set({ activeProfile: toSnapshot(profile) });
        }
      },
      setHasHydrated: (value) => set({ hasHydrated: value }),
    }),
    {
      name: ACTIVE_PROFILE_STORAGE_KEY,
      // Persist only the selection; `hasHydrated` is runtime-only.
      partialize: (state) => ({ activeProfile: state.activeProfile }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true);
      },
    },
  ),
);

/**
 * The active profile id for the HTTP layer to attach as `X-Profile-Id`, or
 * `null` when no profile is selected. Reads the store outside React so it can be
 * called from the framework-agnostic request pipeline.
 */
export function getActiveProfileId(): number | null {
  return useActiveProfileStore.getState().activeProfile?.id ?? null;
}
