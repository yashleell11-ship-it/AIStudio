export type OcrJobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "cancelled";

export interface OcrMetrics {
  jobs: { started: number; completed: number; failed: number };
  pages: { processed: number; skipped: number; retried: number };
  performance: {
    avg_page_ms: number;
    pages_per_sec: number;
    avg_confidence: number;
  };
  retry_rate: number;
  engine_breakdown: Record<string, number>;
}

export interface OcrJob {
  id: number;
  chapter_id: number;
  status: OcrJobStatus;
  engine: string;
  progress: number;
  pages_done: number;
  pages_total: number;
  retry_count: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface OcrSearchResultItem {
  chapter_id: number;
  chapter_title: string;
  chapter_number: number;
  series_id: number;
  series_title: string;
  word_count: number;
  engine: string;
  /** Server-highlighted excerpt containing literal <mark>…</mark> markers. */
  snippet: string;
  highlighted_terms: string[];
}

export interface OcrSearchResponse {
  items: OcrSearchResultItem[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
}
