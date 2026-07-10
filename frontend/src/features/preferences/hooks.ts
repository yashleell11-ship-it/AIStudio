import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { preferencesApi } from "./api";

const PREFERENCES_KEY = ["preferences"] as const;

export function useContentPreferences() {
  return useQuery({
    queryKey: [...PREFERENCES_KEY, "content"],
    queryFn: () => preferencesApi.get(),
  });
}

/**
 * Toggle the mature-content gate. Because the backend filters *which* sources,
 * search results, and recommendations it returns based on this flag, flipping
 * it must invalidate every cache that could now reveal (or need to hide) adult
 * content: the installed-sources list and the discovery/recommendation strips.
 */
export function useSetMatureContent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => preferencesApi.setMatureContent(enabled),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...PREFERENCES_KEY, "content"] });
      void queryClient.invalidateQueries({ queryKey: ["sources"] });
      void queryClient.invalidateQueries({ queryKey: ["intelligence"] });
    },
  });
}
