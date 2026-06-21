export interface Book {
  id: number;
  title: string;
  author?: string | null;
  isbn?: string | null;
  publisher?: string | null;
  pages?: string | null;
  description?: string | null;
  cover_url?: string | null;
  source?: string | null;
  tags: string[];
  latest_progress?: Progress | null;
  notes?: Note[];
}

export interface Progress {
  current_page: number;
  total_pages?: number | null;
  percentage: number;
}

export interface Note {
  id: number;
  text: string;
  note_type: string;
  page?: number | null;
}

export interface UserStats {
  books_count: number;
  notes_count: number;
  total_read_pages: number;
  last_7_days: Array<{ date: string; pages: number }>;
  top_genres: Array<{ tag: string; count: number }>;
}

export interface BookSearchResult {
  title: string;
  author?: string | null;
  isbn?: string | null;
  publisher?: string | null;
  pages?: string | null;
  description?: string | null;
  cover_url?: string | null;
  source?: string | null;
  tags?: string[];
}

export interface ShareInfo {
  share_url: string;
  qr_url: string;
  token: string;
  verified: boolean;
}
