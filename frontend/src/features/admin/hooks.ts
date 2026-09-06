import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isUnauthorizedError } from "@/features/auth/access";
import { AUTH_KEY, CURRENT_USER_QUERY_KEY } from "@/features/auth/hooks";
import { adminApi } from "./api";
import type { MemberAccount } from "./types";

/**
 * Nested under the `auth` root on purpose, not given a root of its own.
 *
 * The member list is account-level data: it is not filtered by any profile's
 * 18+ gate (`NOT_MATURE_GATED_QUERY_ROOTS` in `preferences/mature-gate.ts`)
 * and it does not change when the reader switches profile
 * (`PROFILE_AGNOSTIC_QUERY_ROOTS` in `app/providers.tsx`). `auth` is already
 * on both lists, which is exactly the classification this data needs; a fresh
 * `admin` root would have been wiped on every profile switch for nothing. The
 * endpoints live under `/auth/users`, so the key follows the route.
 *
 * The one cost of the namespace: the global 401 handler skips `auth` keys (it
 * would loop on `/auth/me`), so an expired session has to be reported from
 * `useMembers` itself, the way `useSessions` does.
 */
export const MEMBERS_QUERY_KEY = [...AUTH_KEY, "users"] as const;

/**
 * Every account on the instance. Only fetched for an admin (`enabled`): a
 * non-admin's request would be a guaranteed 403 for a panel that never renders
 * anyway. Never served stale across a mount — a row's `session_count` and
 * `last_login_at` are exactly what the owner opens this table to read. Not
 * retried: a 401 or 403 does not get better on a second try, and the panel
 * has its own "Try again".
 */
export function useMembers(enabled: boolean) {
  const queryClient = useQueryClient();
  return useQuery<MemberAccount[]>({
    queryKey: MEMBERS_QUERY_KEY,
    queryFn: async () => {
      try {
        return await adminApi.users();
      } catch (error) {
        // See the note on MEMBERS_QUERY_KEY: nothing else will notice this 401.
        if (isUnauthorizedError(error)) {
          queryClient.setQueryData(CURRENT_USER_QUERY_KEY, null);
        }
        throw error;
      }
    },
    enabled,
    retry: false,
    staleTime: 0,
  });
}

/**
 * Switch an account on or off. The server returns the updated row, which is
 * written straight into the cached list so the badge flips without a refetch;
 * the list is still invalidated afterwards so `session_count` catches up if
 * deactivating also revoked the account's sessions.
 */
export function useSetMemberActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: number; isActive: boolean }) =>
      adminApi.setActive(userId, isActive),
    onSuccess: (updated) => {
      queryClient.setQueryData<MemberAccount[]>(MEMBERS_QUERY_KEY, (rows) =>
        rows?.map((row) => (row.id === updated.id ? updated : row)),
      );
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}

/** Remove an account and everything it owns. Never called for the caller's own id. */
export function useDeleteMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: number) => adminApi.deleteUser(userId),
    onSuccess: (_result, userId) => {
      queryClient.setQueryData<MemberAccount[]>(MEMBERS_QUERY_KEY, (rows) =>
        rows?.filter((row) => row.id !== userId),
      );
    },
    onSettled: () => {
      // Also on failure: a 404 means the row is already gone, and the table
      // should stop offering to delete it either way.
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}
