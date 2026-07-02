export interface SourceSummary {
  id: string;
  name: string;
  description: string;
  browsable: boolean;
  supports_import: boolean;
}

export interface SourceSeriesSummary {
  id: string;
  source_id: string;
  title: string;
  chapter_count: number;
  description: string | null;
  author: string | null;
  artist: string | null;
  status: string | null;
  genres: string[];
  latest_chapter: string | null;
  cover_url: string;
}

export type SourceSeriesDetail = SourceSeriesSummary;

export interface SourceChapterSummary {
  id: string;
  source_id: string;
  series_id: string;
  title: string;
  number: number | null;
  page_count: number;
  release_date: string | null;
}

export interface PaginatedSourceSeries {
  items: SourceSeriesSummary[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_more: boolean;
}

export interface SourceBrowseMode {
  id: string;
  label: string;
}
