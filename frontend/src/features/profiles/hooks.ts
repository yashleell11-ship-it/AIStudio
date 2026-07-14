import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { profilesApi } from "./api";
import { useActiveProfileStore } from "./store";
import type {
  CreateProfilePayload,
  Profile,
  UpdateProfilePayload,
} from "./types";

export const PROFILES_QUERY_KEY = ["profiles"] as const;

/** All reading profiles for the signed-in account, ordered by `sort_order`. */
export function useProfiles() {
  return useQuery<Profile[]>({
    queryKey: PROFILES_QUERY_KEY,
    queryFn: () => profilesApi.list(),
  });
}

export function useCreateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateProfilePayload) => profilesApi.create(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: PROFILES_QUERY_KEY });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  const syncActiveProfile = useActiveProfileStore((s) => s.syncActiveProfile);
  return useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: UpdateProfilePayload }) =>
      profilesApi.update(id, changes),
    onSuccess: (updated) => {
      // Keep the active-profile snapshot (name/avatar/mood used by the shell
      // tint + switcher) in sync when the profile being edited is the active one.
      syncActiveProfile(updated);
      void queryClient.invalidateQueries({ queryKey: PROFILES_QUERY_KEY });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();
  const activeProfile = useActiveProfileStore((s) => s.activeProfile);
  const clearActiveProfile = useActiveProfileStore((s) => s.clearActiveProfile);
  return useMutation({
    mutationFn: (id: number) => profilesApi.remove(id),
    onSuccess: (_data, id) => {
      // Deleting the active profile drops the selection so the gate returns the
      // user to the picker to choose another.
      if (activeProfile?.id === id) clearActiveProfile();
      void queryClient.invalidateQueries({ queryKey: PROFILES_QUERY_KEY });
    },
  });
}
