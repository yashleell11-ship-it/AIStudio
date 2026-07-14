import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ocrApi } from "./api";
import type { OcrJobStatus } from "./types";

const OCR_KEY = ["ocr"] as const;

export function useOcrMetrics() {
  return useQuery({
    queryKey: [...OCR_KEY, "metrics"],
    queryFn: () => ocrApi.metrics(),
    refetchInterval: 5_000,
  });
}

export function useOcrJobs(status?: OcrJobStatus) {
  return useQuery({
    queryKey: [...OCR_KEY, "jobs", status ?? "all"],
    queryFn: () => ocrApi.jobs(status ? { status, limit: 100 } : { limit: 100 }),
    refetchInterval: 5_000,
  });
}

export function useRetryOcrJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ocrApi.retryJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OCR_KEY });
    },
  });
}

export function useCancelOcrJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ocrApi.cancelJob,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: OCR_KEY });
    },
  });
}

/**
 * Dialogue search over extracted OCR text. Disabled (no request) until a
 * non-empty query is supplied; callers should debounce the raw input before
 * passing it here so keystrokes don't each fire a request.
 */
export function useOcrSearch(query: string) {
  const q = query.trim();
  return useQuery({
    queryKey: [...OCR_KEY, "search", q],
    queryFn: () => ocrApi.search({ q, limit: 20 }),
    enabled: q.length > 0,
  });
}
