"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { KeyboardProvider } from "@/lib/keyboard";

/**
 * Client-side providers shared by the whole app.
 * - TanStack Query owns server/cache state.
 * - KeyboardProvider owns the global shortcut listener.
 * Rendered inside the root layout, wrapping only `children`.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <KeyboardProvider>{children}</KeyboardProvider>
    </QueryClientProvider>
  );
}
