"use client";

import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { KeyboardProvider } from "@/lib/keyboard";
import { setStorageScope } from "@/lib/scoped-storage";
import { isAuthQueryKey, isUnauthorizedError } from "@/features/auth/access";
import { CURRENT_USER_QUERY_KEY, useCurrentUser } from "@/features/auth/hooks";
import { discardLegacyRecentSearches } from "@/features/library/recent-searches";
import { adoptLegacySourceProgress } from "@/features/sources/source-progress";
import { isProfileScopeError, useActiveProfileStore } from "@/features/profiles";

/**
 * Query-key roots that are NOT scoped to the active reading profile and must
 * survive a profile switch: the account session (`auth`) and the account's
 * profile list (`profiles`). Every other cached query holds per-profile data
 * (library, reader, updates/follows, downloads, preferences/mature, …) and is
 * dropped when the active profile changes so profile B never renders profile
 * A's data.
 */
const PROFILE_AGNOSTIC_QUERY_ROOTS = new Set(["auth", "profiles"]);

/** Drop every profile-scoped query so the new profile refetches from scratch. */
function resetProfileScopedQueries(client: QueryClient): void {
  client.removeQueries({
    predicate: (query) =>
      !PROFILE_AGNOSTIC_QUERY_ROOTS.has(query.queryKey[0] as string),
  });
}

/**
 * Build the app's QueryClient with two global error handlers.
 *
 * 401 (session expired): any protected query failing 401 means the session is
 * gone, so we flip the cached current-user to `null`; the AuthGuard reacts by
 * redirecting to /login. Auth-namespace queries are skipped (`/auth/me`
 * resolves 401 to `null` itself, `/auth/bootstrap-status` is public) so this
 * cannot loop.
 *
 * 400 `profile_required` / 404 `profile_not_found`: the remembered profile
 * selection is no longer valid (missing header, or a profile the account no
 * longer owns). We clear the active profile; the shell's profile gate then
 * routes the user back to the picker to re-select, instead of surfacing a raw
 * error. Applied to both reads (QueryCache) and mutations (MutationCache) so a
 * failed follow/progress/collection write recovers the same way.
 *
 * Keeping these in the query layer avoids coupling the framework-agnostic
 * `http` client to React.
 */
function createQueryClient(): QueryClient {
  const queryCache = new QueryCache({
    onError: (error, query) => {
      if (isUnauthorizedError(error) && !isAuthQueryKey(query.queryKey)) {
        client.setQueryData(CURRENT_USER_QUERY_KEY, null);
        return;
      }
      if (isProfileScopeError(error)) {
        useActiveProfileStore.getState().clearActiveProfile();
      }
    },
  });
  const mutationCache = new MutationCache({
    onError: (error) => {
      if (isProfileScopeError(error)) {
        useActiveProfileStore.getState().clearActiveProfile();
      }
    },
  });
  const client = new QueryClient({
    queryCache,
    mutationCache,
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: 1,
      },
    },
  });
  return client;
}

/**
 * Watches the active reading profile and clears profile-scoped caches whenever
 * it switches to a *different* profile (or is cleared). The first observed id —
 * including the hydration of a remembered selection on cold load — is only
 * recorded, never treated as a switch, so a page reload does not needlessly
 * wipe caches that were just populated.
 */
function ProfileCacheBoundary({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const activeId = useActiveProfileStore((s) => s.activeProfile?.id ?? null);
  // `undefined` sentinel = not yet observed; distinct from the `null` "no
  // profile selected" state.
  const previousId = useRef<number | null | undefined>(undefined);

  useEffect(() => {
    const previous = previousId.current;
    previousId.current = activeId;
    // Reset only on a genuine switch away from an already-selected profile.
    // Records first observation and null→id restores without resetting.
    if (previous !== undefined && previous !== null && previous !== activeId) {
      resetProfileScopedQueries(queryClient);
    }
  }, [activeId, queryClient]);

  return <>{children}</>;
}

/**
 * Publishes the (user, profile) that client-side stores namespace their
 * localStorage keys with, and runs the one-time migration of the keys written
 * before the app had profiles.
 *
 * `ProfileCacheBoundary` above drops the *query* cache on a switch; nothing it
 * does touches localStorage, so without this the online reading positions and
 * recent searches of the profile that just left stay readable by the next one.
 * Clearing those keys on switch is not the fix — that would delete each
 * profile's own data every time the browser changes hands.
 *
 * Publishing from an effect is late by one render: a store read during that
 * first pass sees no scope and returns empty, then re-reads when the scope
 * lands (both scoped stores subscribe to scope changes). Reading empty for a
 * frame is the safe direction; reading a shared blob is not.
 *
 * `useCurrentUser` is already mounted by everything rendered below — the
 * shell's route guard and the login/register screens' own session check — so
 * subscribing here costs no extra request.
 */
function ProfileStorageBoundary({ children }: { children: React.ReactNode }) {
  const { data: user } = useCurrentUser();
  const userId = user?.id ?? null;
  const profileId = useActiveProfileStore((s) => s.activeProfile?.id ?? null);

  useEffect(() => {
    if (userId === null || profileId === null) {
      // Signed out, or between profiles: no scope at all, so scoped reads
      // return nothing instead of falling back to a device-global blob.
      setStorageScope(null);
      return;
    }
    setStorageScope({ userId, profileId });
    // Both are no-ops once the pre-scoping key is gone, so running them on
    // every switch costs one miss and needs no "already migrated" flag.
    adoptLegacySourceProgress();
    discardLegacyRecentSearches();
  }, [userId, profileId]);

  return <>{children}</>;
}

/**
 * Client-side providers shared by the whole app.
 * - TanStack Query owns server/cache state.
 * - ProfileCacheBoundary isolates cached data per reading profile.
 * - ProfileStorageBoundary isolates localStorage per reading profile.
 * - KeyboardProvider owns the global shortcut listener.
 * Rendered inside the root layout, wrapping only `children`.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ProfileCacheBoundary>
        <ProfileStorageBoundary>
          <KeyboardProvider>{children}</KeyboardProvider>
        </ProfileStorageBoundary>
      </ProfileCacheBoundary>
    </QueryClientProvider>
  );
}
