export interface ReadingProgress {
  series_id: number;
  chapter_id: number;
  last_page: number;
  progress_pct: number;
  last_read_at: string;
}

export interface SeriesSummary {
  id: number;
  library_id: number;
  title: string;
  sort_title: string;
  original_title: string | null;
  author: string | null;
  artist: string | null;
  description: string | null;
  status: string | null;
  content_rating: string;
  language: string;
  year: number | null;
  cover_path: string | null;
  folder_path: string;
  is_favorite: boolean;
  reading_status: string;
  chapter_count: number;
  read_chapters: number;
  page_count: number;
  total_chapters: number;
  total_pages: number;
  first_chapter_id: number | null;
  created_at: string;
  updated_at: string;
  reading_progress: ReadingProgress | null;
}

export interface SeriesListResponse {
  items: SeriesSummary[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
}

export interface ChapterSummary {
  /** Local chapter id. Null for remote-only chapters not yet downloaded. */
  id: number | null;
  series_id: number;
  title: string;
  number: number | null;
  page_count: number;
  folder_path: string | null;
  archive_path: string | null;
  /** Same as id when a local copy exists; null otherwise. */
  local_chapter_id?: number | null;
  /** Whether a downloaded local copy exists. */
  is_downloaded?: boolean;
  /** Whether the chapter is marked read. */
  is_read?: boolean;
  /** Source chapter id (e.g. 'killer-pietro-a80d257e:2'). Null when unknown. */
  source_chapter_id?: string | null;
}

export interface SeriesDetail extends SeriesSummary {
  chapters: ChapterSummary[];
  tags: Tag[];
  collections: CollectionRef[];
  /** Online source id this series is linked to, or null. */
  source_id?: string | null;
  /** The source's series id, or null. */
  source_series_id?: string | null;
}

export interface PageInfo {
  id: number;
  chapter_id: number;
  number: number;
  file_path: string;
  width: number | null;
  height: number | null;
}

export interface ChapterDetail {
  id: number;
  series_id: number;
  title: string;
  number: number | null;
  page_count: number;
  pages: PageInfo[];
}

export interface ContinueReadingItem {
  series_id: number;
  series_title: string;
  chapter_id: number;
  chapter_title: string;
  last_page: number;
  progress_pct: number;
  last_read_at: string;
  cover_path: string | null;
}

export interface ImportResponse {
  status: string;
  library_id: number;
  series_count: number;
  chapter_count: number;
  page_count: number;
}

export interface ScanStatus {
  running: boolean;
  progress_pct: number;
  message: string;
  series_count: number;
  chapter_count: number;
  page_count: number;
  error: string | null;
}

export type SeriesSort = "title" | "updated" | "recent" | "date_added" | "author" | "year" | "total_chapters";
export type SeriesFilter = "all" | "reading" | "unread";

// --- Collections ---

export interface Collection {
  id: number;
  name: string;
  description: string | null;
  cover_path: string | null;
  series_count: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CollectionRef {
  id: number;
  name: string;
}

export interface CollectionDetail extends Collection {
  series: SeriesListResponse;
}

// --- Tags ---

export interface Tag {
  id: number;
  name: string;
  category: string;
  color: string | null;
  series_count: number;
}

// --- Search ---

export type SearchResponse = SeriesListResponse;

// --- Recommendations ---

export type RecommendationsResponse = SeriesSummary[];

// --- Reading History ---

export interface ReadingHistoryItem {
  session_id: number;
  series_id: number;
  series_title: string | null;
  chapter_id: number;
  chapter_title: string | null;
  start_page: number;
  end_page: number;
  pages_read: number;
  started_at: string | null;
  ended_at: string | null;
}

export interface ReadingCalendarItem {
  day: string;
  sessions: number;
  pages_read: number;
  has_activity: boolean;
}

// --- Statistics ---

export interface Statistics {
  total_series: number;
  total_chapters: number;
  total_pages: number;
  completed_series: number;
  in_progress: number;
  favorites: number;
  completion_rate_pct: number;
  total_reading_time_estimate_minutes: number;
  pages_read_this_week: number;
  reading_streak_days: number;
  reading_velocity_pages_per_hour: number;
  tag_distribution: TagDistributionItem[];
  top_authors: AuthorStat[];
  weekly_chart: WeeklyChartItem[];
}

export interface TagDistributionItem {
  name: string;
  category: string;
  color: string | null;
  series_count: number;
}

export interface AuthorStat {
  author: string;
  series_count: number;
  total_pages: number;
}

export interface WeeklyChartItem {
  day: string;
  label: string;
  pages_read: number;
}

// --- Metadata ---

export interface MetadataQuality {
  series_id: number;
  score: number;
  missing: string[];
  suggestions: string[];
  fields: Record<string, boolean>;
}
