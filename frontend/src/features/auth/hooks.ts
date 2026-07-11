import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/types/api";
import { authApi } from "./api";
import type { LoginPayload, RegisterPayload, User } from "./types";

export const AUTH_KEY = ["auth"] as const;
/** The single source of truth for "who is signed in" — read by the guard, menu, and sidebar. */
export const CURRENT_USER_QUERY_KEY = [...AUTH_KEY, "me"] as const;
export const BOOTSTRAP_QUERY_KEY = [...AUTH_KEY, "bootstrap"] as const;

/**
 * The current signed-in user, or `null` when not authenticated. A 401 from
 * `/auth/me` is the normal "not signed in" outcome, so it resolves to `null`
 * rather than throwing; we never retry the probe.
 */
export function useCurrentUser() {
  return useQuery<User | null>({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: async () => {
      try {
        return await authApi.me();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** Public bootstrap/registration gate used by the login and register screens. */
export function useBootstrapStatus() {
  return useQuery({
    queryKey: BOOTSTRAP_QUERY_KEY,
    queryFn: () => authApi.bootstrapStatus(),
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: LoginPayload) => authApi.login(payload),
    onSuccess: (data) => {
      // Seed the current-user cache directly so the guard admits the app
      // immediately, without a redundant /auth/me round-trip.
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, data.user);
    },
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisterPayload) => authApi.register(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, data.user);
      // Creating the first account flips `needs_bootstrap`; keep the gate fresh.
      void queryClient.invalidateQueries({ queryKey: BOOTSTRAP_QUERY_KEY });
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => authApi.logout(),
    // Runs on success and error: even if the cookie was already invalid we
    // still drop every cached query (so the next user starts clean) and mark
    // the session as signed out.
    onSettled: () => {
      queryClient.removeQueries();
      queryClient.setQueryData(CURRENT_USER_QUERY_KEY, null);
    },
  });
}
