import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useActiveProfileStore } from "@/features/profiles/store";
import { ApiError } from "@/types/api";
import { preferencesApi } from "./api";
import {
  invalidateMatureGatedQueries,
  matureToggleBlockReason,
} from "./mature-gate";

const PREFERENCES_KEY = ["preferences"] as const;

export function useContentPreferences() {
  return useQuery({
    queryKey: [...PREFERENCES_KEY, "content"],
    queryFn: () => preferencesApi.get(),
  });
}

/**
 * Why the mature toggle is currently unwritable, or null. Panels use this to
 * disable the control and explain it, rather than letting the user flip a
 * switch whose write would land somewhere else — see `mature-gate.ts`.
 */
export function useMatureToggleBlockReason(): string | null {
  const profileId = useActiveProfileStore((state) => state.activeProfile?.id ?? null);
  return matureToggleBlockReason(profileId);
}

/**
 * Toggle the mature-content gate for the ACTIVE PROFILE.
 *
 * Refuses without one: `PUT /settings` silently retargets the instance-wide
 * default when no `X-Profile-Id` is attached (see `mature-gate.ts`). The
 * refusal is raised as the backend's own `profile_required` error so the app's
 * existing recovery — drop the stale selection, send the user to the picker —
 * applies here exactly as it does to a write the server rejects.
 *
 * Because the backend filters *which* sources, search results, library rows,
 * continue-reading entries and recommendations it returns based on this flag, a
 * successful flip must invalidate every cache that could now reveal (or need to
 * hide) adult content — see `MATURE_GATED_QUERY_ROOTS`.
 */
export function useSetMatureContent() {
  const queryClient = useQueryClient();
  const blockReason = useMatureToggleBlockReason();
  return useMutation({
    mutationFn: (enabled: boolean) => {
      if (blockReason) {
        return Promise.reject(
          new ApiError(400, { code: "profile_required", message: blockReason }),
        );
      }
      return preferencesApi.setMatureContent(enabled);
    },
    onSuccess: () => invalidateMatureGatedQueries(queryClient),
  });
}
