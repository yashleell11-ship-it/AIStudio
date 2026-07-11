"use client";

import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { KeyboardProvider } from "@/lib/keyboard";
import { isAuthQueryKey, isUnauthorizedError } from "@/features/auth/access";
import { CURRENT_USER_QUERY_KEY } from "@/features/auth/hooks";

/**
 * Build the app's QueryClient with a global 401 handler. When any protected
 * query fails with 401 the session has expired, so we flip the cached
 * current-user to `null`; the AuthGuard reacts by redirecting to /login via the
 * SPA router. Auth-namespace queries are skipped: `/auth/me` resolves 401 to
 * `null` itself (never erroring here) and `/auth/bootstrap-status` is public,
 * so this cannot loop. Keeping the redirect in the auth/query layer avoids
 * coupling the framework-agnostic `http` client to React.
 */
function createQueryClient(): QueryClient {
  const queryCache = new QueryCache({
    onError: (error, query) => {
      if (isUnauthorizedError(error) && !isAuthQueryKey(query.queryKey)) {
        client.setQueryData(CURRENT_USER_QUERY_KEY, null);
      }
    },
  });
  const client = new QueryClient({
    queryCache,
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
 * Client-side providers shared by the whole app.
 * - TanStack Query owns server/cache state.
 * - KeyboardProvider owns the global shortcut listener.
 * Rendered inside the root layout, wrapping only `children`.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <KeyboardProvider>{children}</KeyboardProvider>
    </QueryClientProvider>
  );
}
