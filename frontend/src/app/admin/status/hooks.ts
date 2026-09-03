"use client";

import { useQuery } from "@tanstack/react-query";
import { statusApi } from "./api";

/**
 * Backend liveness, polled.
 *
 * `retry: false` on purpose: a failed probe IS the answer this page exists to
 * show, and react-query's default backoff would leave the card reading
 * "loading" for several seconds after the server went away.
 */
export function useBackendHealth() {
  return useQuery({
    queryKey: ["status", "health"],
    queryFn: () => statusApi.health(),
    refetchInterval: 15_000,
    retry: false,
  });
}

/** Per-source reachability, worst-first (GET /sources/health). */
export function useSourceHealth() {
  return useQuery({
    queryKey: ["status", "source-health"],
    queryFn: () => statusApi.sourceHealth(),
    refetchInterval: 30_000,
  });
}
