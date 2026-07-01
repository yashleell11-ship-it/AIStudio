import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { downloadsApi } from "./api";

const DOWNLOADS_KEY = ["downloads"] as const;

export function useDownloadMetrics() {
  return useQuery({
    queryKey: [...DOWNLOADS_KEY, "metrics"],
    queryFn: () => downloadsApi.metrics(),
    refetchInterval: 5000,
  });
}

export function useDownloads() {
  return useQuery({
    queryKey: DOWNLOADS_KEY,
    queryFn: () => downloadsApi.list(),
    refetchInterval: (query) => {
      const items = query.state.data ?? [];
      const active = items.some((item) =>
        ["queued", "downloading"].includes(item.status),
      );
      return active ? 2000 : false;
    },
  });
}

export function useQueueChapters() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.queueChapters,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useQueueSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.queueSeries,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function usePauseDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.pause,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useResumeDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.resume,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useCancelDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.cancel,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useRetryDownload() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.retry,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function usePauseSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.pauseSeries,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useResumeSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.resumeSeries,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useCancelSeries() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.cancelSeries,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function usePauseAllDownloads() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.pauseAll,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useResumeAllDownloads() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.resumeAll,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useCancelAllDownloads() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.cancelAll,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: DOWNLOADS_KEY });
    },
  });
}

export function useDownloadSettings() {
  return useQuery({
    queryKey: [...DOWNLOADS_KEY, "settings"],
    queryFn: () => downloadsApi.getSettings(),
    refetchInterval: 5000,
  });
}

export function useUpdateDownloadSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: downloadsApi.updateSettings,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...DOWNLOADS_KEY, "settings"] });
    },
  });
}
