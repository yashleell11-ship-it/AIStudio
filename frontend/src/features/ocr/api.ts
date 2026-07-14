import { http } from "@/services/http";
import type { OcrJob, OcrJobStatus, OcrMetrics, OcrSearchResponse } from "./types";

export const ocrApi = {
  metrics: () => http.get<OcrMetrics>("/ocr/metrics"),

  jobs: (params?: { status?: OcrJobStatus; limit?: number }) =>
    http.get<OcrJob[]>("/ocr/jobs", { query: params }),

  retryJob: (jobId: number) => http.post<OcrJob>(`/ocr/jobs/${jobId}/retry`),

  cancelJob: (jobId: number) => http.post<OcrJob>(`/ocr/jobs/${jobId}/cancel`),

  search: (params: { q: string; limit?: number; offset?: number }) =>
    http.get<OcrSearchResponse>("/ocr/search", { query: params }),
};
