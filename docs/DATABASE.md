# AIStudio — Production Database Schema

**Status:** Canonical reference. All SQLAlchemy models must exactly match this document.
**Cross-references:** [ARCHITECTURE.md](ARCHITECTURE.md) · [ROADMAP.md](ROADMAP.md) · [PROJECT_RULES.md](PROJECT_RULES.md)

---

## 1. Design Goals

| Goal | How it is achieved |
|------|--------------------|
| Scale to 100K+ chapters, millions of pages | BIGINT PKs on high-cardinality tables; every FK column indexed |
| Sub-200ms library load | Denormalized counts on `series`; partial indexes; paginated queries only |
| PostgreSQL-ready from day one | No SQLite-isms; BLOB vectors swap to `pgvector` with zero code change |
| AI-generated content is always correctable | Every AI-generated row carries `is_ai_generated` + `is_user_edited` flags |
| Reading progress survives restarts | Two-level progress: series-level resume + chapter-level scroll position |
| FTS5 full-text search over OCR, series, and summaries | Three virtual tables kept in sync via triggers |
| Offline-first | No network-dependent columns; all paths are local absolute paths |

---

## 2. Technology Notes

- **SQLite** is the deployment target for Phases 1–5. Every connection must run
  `PRAGMA foreign_keys = ON` and `PRAGMA journal_mode = WAL`.
- **PostgreSQL** is the Phase 6+ target. The connection string is the only change.
  SQLAlchemy ORM handles all dialect differences automatically.
- **Timestamps** are stored as `TIMESTAMPTZ` (SQLAlchemy `DateTime(timezone=True)`).
  SQLite stores these as ISO 8601 strings; PostgreSQL handles them natively.
- **BOOLEAN** columns are `INTEGER` in SQLite (`0`/`1`). SQLAlchemy maps `Boolean`
  transparently on both databases.
- **BIGINT** primary keys are used on tables expected to exceed one million rows:
  `pages`, `ocr_pages`, `embedding_chunks`, `embeddings`, `character_appearances`,
  `ai_chat_messages`, `reading_sessions`.
- **FTS5 virtual tables** are SQLite-only. On PostgreSQL, replace with
  `tsvector` columns and `GIN` indexes. Application logic is identical.
- **Vector embeddings** are stored as `BLOB` (raw `float32` bytes) in SQLite.
  On PostgreSQL, the column type swaps to `pgvector`'s `VECTOR(N)`. No other change.

---

## 3. Entity Relationship Overview

```
libraries ──< series >── volumes
                │
                ├──< chapters >── pages ──< ocr_pages
                │                               │
                │                         embedding_chunks ── embeddings
                │
                ├──< reading_progress (series-level resume)
                ├──< chapter_progress (page + scroll)
                ├──< reading_sessions (statistics)
                ├──< bookmarks
                │
                ├──< characters ──< character_aliases
                │        │        < character_relationships
                │        └──< character_appearances
                │        └──< character_factions >── world_factions
                │
                ├──< timeline_events >── timeline_event_characters
                ├──< world_locations (hierarchical, parent_id)
                ├──< world_factions  (hierarchical, parent_id)
                ├──< world_lore
                ├──< story_scenes >── story_scene_characters
                │
                ├──< ai_summaries
                ├──< ai_chat_sessions ──< ai_chat_messages
                ├──< series_ai_status
                │
                ├── collection_series >── collections
                └── series_tags      >── tags

series_fts   (FTS5, mirrors series)
ocr_fts      (FTS5, mirrors ocr_pages)
summary_fts  (FTS5, mirrors ai_summaries)

import_history ── libraries
background_tasks (generic task queue)

download_sources ──< download_jobs ── series

creation_projects ──< project_characters ──< generated_assets
                  ──< project_chapters   ──< project_panels ── generated_assets
                  ──< generated_assets
                  ── comfyui_workflows

users ──< user_sessions
users  ── reading_progress (Phase 6: add user_id FK)

settings (key-value, no FK)
```

---

## 4. Schema

The tables are grouped by domain. Phase labels indicate when each table is first needed.

---

### 4.1 Library Root Paths

```sql
-- Phase 2
-- Root paths registered by the user. All series must live under a library root.
CREATE TABLE libraries (
    id                      INTEGER PRIMARY KEY,
    name                    TEXT        NOT NULL,
    root_path               TEXT        NOT NULL UNIQUE, -- absolute, pre-validated path
    is_active               INTEGER     NOT NULL DEFAULT 1,
    scan_interval_minutes   INTEGER     NOT NULL DEFAULT 60,
    last_scanned_at         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

### 4.2 Series

```sql
-- Phase 2
-- One row per manga/manhwa/manhua series. The central entity.
CREATE TABLE series (
    id              INTEGER     PRIMARY KEY,
    library_id      INTEGER     NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,

    -- Identity
    title           TEXT        NOT NULL,
    sort_title      TEXT        NOT NULL,   -- normalized: strip "The", lowercase, no leading articles
    original_title  TEXT,                   -- non-English title when available
    author          TEXT,
    artist          TEXT,
    description     TEXT,

    -- Classification
    status          TEXT        NOT NULL DEFAULT 'unknown',
        -- 'ongoing' | 'completed' | 'hiatus' | 'cancelled' | 'unknown'
    content_rating  TEXT        NOT NULL DEFAULT 'unknown',
        -- 'safe' | 'suggestive' | 'adult' | 'unknown'
    language        TEXT        NOT NULL DEFAULT 'ko', -- ISO 639-1
    year            INTEGER,

    -- File system
    cover_path      TEXT,       -- path relative to AIStudio root (covers/<series_id>.jpg)
    folder_path     TEXT UNIQUE, -- root folder (NULL for archive-only series)

    -- User state
    is_favorite     INTEGER     NOT NULL DEFAULT 0,
    reading_status  TEXT        NOT NULL DEFAULT 'unread',
        -- 'unread' | 'reading' | 'completed' | 'on_hold' | 'dropped' | 'plan_to_read'

    -- Denormalized counts (updated by scanner; avoids COUNT(*) on every library load)
    total_chapters  INTEGER     NOT NULL DEFAULT 0,
    read_chapters   INTEGER     NOT NULL DEFAULT 0,
    total_pages     INTEGER     NOT NULL DEFAULT 0,

    -- Origin
    is_created      INTEGER     NOT NULL DEFAULT 0, -- 1 = created via Creation Studio

    -- Soft delete (preserves reading progress, bookmarks on accidental scan removal)
    deleted_at      TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_series_library_id     ON series(library_id);
CREATE INDEX idx_series_sort_title     ON series(sort_title);
CREATE INDEX idx_series_reading_status ON series(reading_status);
CREATE INDEX idx_series_is_favorite    ON series(is_favorite) WHERE is_favorite = 1;
CREATE INDEX idx_series_updated_at     ON series(updated_at DESC);
-- Partial index on soft-delete column: live rows only
CREATE INDEX idx_series_live           ON series(library_id, sort_title) WHERE deleted_at IS NULL;
```

---

### 4.3 Volumes

```sql
-- Phase 2
-- Optional grouping between series and chapters (volume 1, volume 2, etc.).
-- Many series have no volume structure; chapters FK directly to series.
CREATE TABLE volumes (
    id          INTEGER     PRIMARY KEY,
    series_id   INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    number      REAL        NOT NULL,       -- 1.0, 2.0, 2.5 (omnibus/special volumes)
    title       TEXT,
    cover_path  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX       idx_volumes_series_id     ON volumes(series_id);
CREATE UNIQUE INDEX idx_volumes_series_number ON volumes(series_id, number);
```

---

### 4.4 Chapters

```sql
-- Phase 2
-- One reading unit: a folder, a CBZ/CBR archive, or a PDF file.
-- This is the primary unit of reading and progress tracking.
CREATE TABLE chapters (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    volume_id       INTEGER     REFERENCES volumes(id) ON DELETE SET NULL,

    -- Identity
    title           TEXT,
    number          REAL        NOT NULL,   -- 1.0, 1.5, 100.5 (side stories, specials)
    -- Zero-padded string for stable lexicographic sort: "0001.500"
    -- Pre-computed on insert; avoids CAST in ORDER BY across millions of rows
    sort_key        TEXT        NOT NULL,

    -- Source (exactly one of these is non-NULL)
    source_type     TEXT        NOT NULL,   -- 'folder' | 'cbz' | 'cbr' | 'pdf'
    folder_path     TEXT UNIQUE,            -- absolute path (folder type)
    archive_path    TEXT UNIQUE,            -- absolute path (cbz/cbr type)
    pdf_path        TEXT UNIQUE,            -- absolute path (pdf type)

    -- Content metadata
    page_count      INTEGER     NOT NULL DEFAULT 0,
    cover_path      TEXT,                   -- relative to AIStudio root
    file_hash       TEXT(64),               -- SHA-256 hex of archive/pdf (dedup + change detection)
    file_size_bytes BIGINT,

    -- Reading state
    is_read         INTEGER     NOT NULL DEFAULT 0,
    read_at         TIMESTAMPTZ,

    -- Scan bookkeeping
    scanned_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        (source_type = 'folder'  AND folder_path  IS NOT NULL) OR
        (source_type = 'cbz'     AND archive_path IS NOT NULL) OR
        (source_type = 'cbr'     AND archive_path IS NOT NULL) OR
        (source_type = 'pdf'     AND pdf_path     IS NOT NULL)
    )
);

-- Primary read-order query: GET /library/series/{id} chapters
CREATE INDEX       idx_chapters_series_sort    ON chapters(series_id, sort_key);
CREATE INDEX       idx_chapters_volume_id      ON chapters(volume_id);
-- For incremental scan: "has this folder already been imported?"
CREATE INDEX       idx_chapters_file_hash      ON chapters(file_hash) WHERE file_hash IS NOT NULL;
```

---

### 4.5 Pages

```sql
-- Phase 2
-- Individual image frames within a chapter.
-- Largest table: expect 5–10 million rows at full scale.
-- BIGINT primary key. Keep this table lean — no text blobs.
CREATE TABLE pages (
    id              BIGINT      PRIMARY KEY,
    chapter_id      INTEGER     NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    page_number     INTEGER     NOT NULL,   -- 1-based, display order

    -- Source (only one set is non-NULL depending on chapter.source_type)
    file_path       TEXT,                   -- absolute path (folder type)
    archive_entry   TEXT,                   -- path inside archive (cbz/cbr type)
    pdf_page        INTEGER,                -- page number within PDF

    -- Image metadata (populated by scanner; NULL until measured)
    width           INTEGER,
    height          INTEGER,
    file_size_bytes INTEGER,
    mime_type       TEXT        NOT NULL DEFAULT 'image/jpeg',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(chapter_id, page_number)
);

-- The only query pattern on this table: get ordered pages for a chapter
CREATE INDEX idx_pages_chapter_id ON pages(chapter_id);
```

---

### 4.6 Reading Progress

```sql
-- Phase 2
-- Series-level resume state: "continue reading" on the Library homepage.
-- One row per series. Single-user in Phases 2–5; Phase 6 adds user_id FK.
CREATE TABLE reading_progress (
    id                  INTEGER     PRIMARY KEY,
    series_id           INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    -- ON DELETE SET NULL rather than RESTRICT: if the chapter is removed by an
    -- incremental rescan, reading_progress survives and the service resolves the
    -- next available chapter on next access.
    current_chapter_id  INTEGER     REFERENCES chapters(id) ON DELETE SET NULL,
    current_page        INTEGER     NOT NULL DEFAULT 1,
    scroll_offset_px    INTEGER     NOT NULL DEFAULT 0, -- webtoon mode: pixels from top
    -- Completion of the whole series (updated on chapter_progress.is_completed flip)
    progress_pct        REAL        NOT NULL DEFAULT 0.0, -- 0.0 to 100.0
    started_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_read_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(series_id)   -- one resume point per series
);

-- Powers the "continue reading" strip ordered by most recently read
CREATE INDEX idx_reading_progress_last_read ON reading_progress(last_read_at DESC);
```

```sql
-- Phase 2
-- Chapter-level state: exact page and scroll position within one chapter.
-- Allows resuming mid-chapter in both manga and webtoon modes.
CREATE TABLE chapter_progress (
    id                  INTEGER     PRIMARY KEY,
    chapter_id          INTEGER     NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    last_page           INTEGER     NOT NULL DEFAULT 1,
    scroll_offset_px    INTEGER     NOT NULL DEFAULT 0, -- webtoon: pixels from top of first image
    is_completed        INTEGER     NOT NULL DEFAULT 0,
    time_spent_seconds  INTEGER     NOT NULL DEFAULT 0, -- accumulated reading time this chapter
    started_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at        TIMESTAMPTZ,
    last_read_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(chapter_id)
);

CREATE INDEX idx_chapter_progress_chapter_id ON chapter_progress(chapter_id);
```

```sql
-- Phase 6
-- One row per reading session (open → close). Source of truth for statistics:
-- pages per day, time spent, streaks.
CREATE TABLE reading_sessions (
    id          BIGINT      PRIMARY KEY,
    series_id   INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    chapter_id  INTEGER     NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    start_page  INTEGER     NOT NULL DEFAULT 1,
    end_page    INTEGER     NOT NULL DEFAULT 1,
    pages_read  INTEGER     NOT NULL DEFAULT 0,
    started_at  TIMESTAMPTZ NOT NULL,
    ended_at    TIMESTAMPTZ
);

CREATE INDEX idx_reading_sessions_series  ON reading_sessions(series_id);
CREATE INDEX idx_reading_sessions_chapter ON reading_sessions(chapter_id);
CREATE INDEX idx_reading_sessions_started ON reading_sessions(started_at DESC);
```

---

### 4.7 Bookmarks

```sql
-- Phase 2
-- User-placed markers on specific pages within any chapter.
CREATE TABLE bookmarks (
    id          INTEGER     PRIMARY KEY,
    series_id   INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    chapter_id  INTEGER     NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    page_id     BIGINT      REFERENCES pages(id)             ON DELETE SET NULL,
    page_number INTEGER     NOT NULL,
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bookmarks_series_id  ON bookmarks(series_id);
CREATE INDEX idx_bookmarks_chapter_id ON bookmarks(chapter_id);
```

---

### 4.8 Collections and Tags

```sql
-- Phase 2
-- User-curated groupings of series (e.g., "Gate-style isekai", "Art study references").
CREATE TABLE collections (
    id          INTEGER     PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    description TEXT,
    cover_path  TEXT,
    sort_order  INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Many-to-many: a series can be in multiple collections.
CREATE TABLE collection_series (
    collection_id   INTEGER     NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    series_id       INTEGER     NOT NULL REFERENCES series(id)      ON DELETE CASCADE,
    sort_order      INTEGER     NOT NULL DEFAULT 0,
    added_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (collection_id, series_id)
);

CREATE INDEX idx_collection_series_series_id ON collection_series(series_id);
```

```sql
-- Phase 2
-- Labels applied to series. Tags have a category to support filtering.
CREATE TABLE tags (
    id          INTEGER     PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    category    TEXT        NOT NULL DEFAULT 'custom',
        -- 'genre' | 'theme' | 'demographic' | 'content_warning' | 'custom'
    color       TEXT,       -- hex color string for display badges
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Many-to-many: a series can have many tags; a tag can apply to many series.
CREATE TABLE series_tags (
    series_id       INTEGER NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    tag_id          INTEGER NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    is_ai_generated INTEGER NOT NULL DEFAULT 0, -- 1 = auto-tagged by AI
    confidence      REAL,       -- AI confidence score (NULL for manual tags)
    PRIMARY KEY (series_id, tag_id)
);

CREATE INDEX idx_series_tags_tag_id ON series_tags(tag_id);
```

---

### 4.9 Import History and Background Task Queue

```sql
-- Phase 2
-- Audit log for every scan/import operation.
CREATE TABLE import_history (
    id              INTEGER     PRIMARY KEY,
    library_id      INTEGER     NOT NULL REFERENCES libraries(id) ON DELETE CASCADE,
    folder_path     TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',
        -- 'pending' | 'running' | 'completed' | 'failed'
    trigger         TEXT        NOT NULL DEFAULT 'manual',
        -- 'manual' | 'startup' | 'scheduled' | 'file_watch'
    series_added    INTEGER     NOT NULL DEFAULT 0,
    series_updated  INTEGER     NOT NULL DEFAULT 0,
    chapters_added  INTEGER     NOT NULL DEFAULT 0,
    pages_added     INTEGER     NOT NULL DEFAULT 0,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX idx_import_history_library_id ON import_history(library_id);
CREATE INDEX idx_import_history_status     ON import_history(status);
CREATE INDEX idx_import_history_started_at ON import_history(started_at DESC);
```

```sql
-- Phase 2
-- Central queue for all background operations (scan, OCR, embed, thumbnail, download).
-- Background workers INSERT jobs; the API polls this table for progress reporting.
CREATE TABLE background_tasks (
    id              INTEGER     PRIMARY KEY,
    task_type       TEXT        NOT NULL,
        -- 'scan' | 'thumbnail' | 'ocr' | 'embed' | 'summarize' | 'knowledge' | 'download'
    status          TEXT        NOT NULL DEFAULT 'pending',
        -- 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
    priority        INTEGER     NOT NULL DEFAULT 5,  -- 1 = highest, 10 = lowest
    -- Polymorphic subject (avoids a separate queue table per task type)
    subject_type    TEXT,       -- 'series' | 'chapter' | 'page' | 'library' | NULL
    subject_id      BIGINT,     -- ID in the relevant table
    payload         TEXT,       -- JSON: task-specific parameters
    progress_pct    REAL        NOT NULL DEFAULT 0.0,
    progress_detail TEXT,       -- human-readable: "Page 42 of 80"
    error_message   TEXT,
    retry_count     INTEGER     NOT NULL DEFAULT 0,
    max_retries     INTEGER     NOT NULL DEFAULT 3,
    scheduled_at    TIMESTAMPTZ,    -- NULL = run immediately; future = deferred
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_background_tasks_status      ON background_tasks(status, priority);
CREATE INDEX idx_background_tasks_type_status ON background_tasks(task_type, status);
CREATE INDEX idx_background_tasks_subject     ON background_tasks(subject_type, subject_id);
-- For deferred tasks: "which tasks are due to run now?"
CREATE INDEX idx_background_tasks_scheduled
    ON background_tasks(scheduled_at)
    WHERE scheduled_at IS NOT NULL AND status = 'pending';
```

---

### 4.10 AI Summaries

```sql
-- Phase 3
-- AI-generated and user-edited summaries at chapter, volume, and series level.
CREATE TABLE ai_summaries (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    chapter_id      INTEGER     REFERENCES chapters(id)          ON DELETE CASCADE,
        -- NULL = series-level or volume-level summary
    summary_type    TEXT        NOT NULL DEFAULT 'chapter',
        -- 'chapter' | 'volume' | 'series' | 'arc'
    content         TEXT        NOT NULL,
    model           TEXT        NOT NULL,       -- model that generated this
    prompt_version  TEXT        NOT NULL DEFAULT '1', -- bump to trigger regeneration
    word_count      INTEGER,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    -- Whether this summary contains content past the user's current read position
    has_spoilers    INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- One summary of each type per chapter (when chapter_id IS NOT NULL)
    -- NULL != NULL in SQL, so this UNIQUE does not enforce uniqueness for series-level
    -- summaries (chapter_id IS NULL). The partial indexes below fill that gap.
    UNIQUE(chapter_id, summary_type)
);

CREATE INDEX idx_ai_summaries_series_id  ON ai_summaries(series_id);
CREATE INDEX idx_ai_summaries_chapter_id ON ai_summaries(chapter_id);
-- Enforce one series-level summary of each type (chapter_id IS NULL case)
CREATE UNIQUE INDEX idx_ai_summaries_series_type
    ON ai_summaries(series_id, summary_type)
    WHERE chapter_id IS NULL;
```

---

### 4.11 OCR

```sql
-- Phase 3
-- Extracted text for each page. One-to-one with pages.
-- BIGINT primary key to match pages table scale (millions of rows expected).
CREATE TABLE ocr_pages (
    id                  BIGINT      PRIMARY KEY,
    page_id             BIGINT      NOT NULL REFERENCES pages(id) ON DELETE CASCADE UNIQUE,
    text_content        TEXT        NOT NULL,   -- raw extracted text
    confidence          REAL,                   -- 0.0 to 1.0 OCR model confidence
    language_detected   TEXT,                   -- ISO 639-1 code detected by model
    model               TEXT        NOT NULL,
    ocr_version         TEXT        NOT NULL DEFAULT '1', -- bump to re-OCR with better model
    word_count          INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ocr_pages_page_id ON ocr_pages(page_id);
```

```sql
-- Phase 3
-- Denormalized per-chapter OCR completion status.
-- Avoids COUNT(*) / COUNT(*) joins on every series detail page load.
CREATE TABLE chapter_ocr_status (
    chapter_id      INTEGER     PRIMARY KEY REFERENCES chapters(id) ON DELETE CASCADE,
    total_pages     INTEGER     NOT NULL DEFAULT 0,
    ocr_pages_done  INTEGER     NOT NULL DEFAULT 0,
    is_complete     INTEGER     NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

```sql
-- Phase 3
-- Per-series pipeline status for the AI analysis UI dashboard.
-- Updated by workers; prevents N+1 queries on the library grid.
CREATE TABLE series_ai_status (
    series_id               INTEGER     PRIMARY KEY REFERENCES series(id) ON DELETE CASCADE,
    -- OCR
    ocr_started_at          TIMESTAMPTZ,
    ocr_completed_at        TIMESTAMPTZ,
    ocr_pct                 REAL        NOT NULL DEFAULT 0.0,
    -- Embedding
    embed_started_at        TIMESTAMPTZ,
    embed_completed_at      TIMESTAMPTZ,
    embed_pct               REAL        NOT NULL DEFAULT 0.0,
    -- Summarization
    summary_started_at      TIMESTAMPTZ,
    summary_completed_at    TIMESTAMPTZ,
    summary_pct             REAL        NOT NULL DEFAULT 0.0,
    -- Knowledge extraction (characters, timeline, world)
    knowledge_extracted_at  TIMESTAMPTZ,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

### 4.12 Full-Text Search (FTS5 Virtual Tables)

FTS5 virtual tables mirror their source tables via triggers so that INSERTs,
UPDATEs, and DELETEs are reflected immediately in search indexes.

**PostgreSQL migration:** replace these three virtual tables with `tsvector`
columns on the source tables, indexed with `GIN`. The service layer's query
changes from `WHERE ocr_fts MATCH ?` to `WHERE ts @@ to_tsquery(?)`.

```sql
-- Phase 3: Full-text search over OCR-extracted text
CREATE VIRTUAL TABLE ocr_fts USING fts5(
    text_content,
    content     = 'ocr_pages',
    content_rowid = 'id',
    tokenize    = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER ocr_fts_ai AFTER INSERT ON ocr_pages BEGIN
    INSERT INTO ocr_fts(rowid, text_content) VALUES (new.id, new.text_content);
END;
CREATE TRIGGER ocr_fts_ad AFTER DELETE ON ocr_pages BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text_content)
    VALUES ('delete', old.id, old.text_content);
END;
CREATE TRIGGER ocr_fts_au AFTER UPDATE ON ocr_pages BEGIN
    INSERT INTO ocr_fts(ocr_fts, rowid, text_content)
    VALUES ('delete', old.id, old.text_content);
    INSERT INTO ocr_fts(rowid, text_content) VALUES (new.id, new.text_content);
END;
```

```sql
-- Phase 2: Full-text search over series titles and descriptions
CREATE VIRTUAL TABLE series_fts USING fts5(
    title, original_title, author, artist, description,
    content       = 'series',
    content_rowid = 'id',
    tokenize      = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER series_fts_ai AFTER INSERT ON series BEGIN
    INSERT INTO series_fts(rowid, title, original_title, author, artist, description)
    VALUES (new.id, new.title, new.original_title, new.author, new.artist, new.description);
END;
CREATE TRIGGER series_fts_ad AFTER DELETE ON series BEGIN
    INSERT INTO series_fts(series_fts, rowid, title, original_title, author, artist, description)
    VALUES ('delete', old.id, old.title, old.original_title, old.author, old.artist, old.description);
END;
CREATE TRIGGER series_fts_au AFTER UPDATE ON series BEGIN
    INSERT INTO series_fts(series_fts, rowid, title, original_title, author, artist, description)
    VALUES ('delete', old.id, old.title, old.original_title, old.author, old.artist, old.description);
    INSERT INTO series_fts(rowid, title, original_title, author, artist, description)
    VALUES (new.id, new.title, new.original_title, new.author, new.artist, new.description);
END;
```

```sql
-- Phase 3: Full-text search over AI-generated and user-edited summaries
CREATE VIRTUAL TABLE summary_fts USING fts5(
    content,
    content       = 'ai_summaries',
    content_rowid = 'id',
    tokenize      = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER summary_fts_ai AFTER INSERT ON ai_summaries BEGIN
    INSERT INTO summary_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER summary_fts_ad AFTER DELETE ON ai_summaries BEGIN
    INSERT INTO summary_fts(summary_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
END;
CREATE TRIGGER summary_fts_au AFTER UPDATE ON ai_summaries BEGIN
    INSERT INTO summary_fts(summary_fts, rowid, content)
    VALUES ('delete', old.id, old.content);
    INSERT INTO summary_fts(rowid, content) VALUES (new.id, new.content);
END;
```

---

### 4.13 Embeddings

```sql
-- Phase 3
-- Text chunks produced from OCR and summary text before embedding.
-- A single OCR page may produce multiple chunks (sliding window, max ~512 tokens).
-- Separating chunks from embeddings allows re-embedding with a better model
-- without discarding the chunk text.
CREATE TABLE embedding_chunks (
    id          BIGINT      PRIMARY KEY,
    source_type TEXT        NOT NULL,
        -- 'ocr_page' | 'summary' | 'character' | 'lore' | 'world'
    source_id   BIGINT      NOT NULL,   -- PK in the source table
    series_id   INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    chunk_index INTEGER     NOT NULL DEFAULT 0,  -- position within the source document
    chunk_text  TEXT        NOT NULL,
    token_count INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source_type, source_id, chunk_index)
);

CREATE INDEX idx_embedding_chunks_source ON embedding_chunks(source_type, source_id);
CREATE INDEX idx_embedding_chunks_series ON embedding_chunks(series_id);
```

```sql
-- Phase 3
-- One vector per chunk. Stored as raw float32 bytes (BLOB).
-- PostgreSQL migration: column type changes to pgvector's VECTOR(dimensions).
-- Query changes from Python cosine similarity (numpy) to PostgreSQL's <=> operator.
CREATE TABLE embeddings (
    id          BIGINT      PRIMARY KEY,
    chunk_id    BIGINT      NOT NULL REFERENCES embedding_chunks(id) ON DELETE CASCADE UNIQUE,
    model       TEXT        NOT NULL,   -- embedding model name (e.g., 'nomic-embed-text')
    dimensions  INTEGER     NOT NULL,   -- vector dimension count (e.g., 768)
    vector      BLOB        NOT NULL,   -- float32[dimensions] as raw bytes
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_embeddings_model ON embeddings(model);
```

---

### 4.14 Characters

```sql
-- Phase 3 (extraction) / Phase 4 (full profiles)
-- Character profiles built from OCR extraction and manual editing.
CREATE TABLE characters (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,   -- canonical name
    role            TEXT        NOT NULL DEFAULT 'unknown',
        -- 'protagonist' | 'antagonist' | 'supporting' | 'minor' | 'unknown'
    description     TEXT,
    appearance      TEXT,       -- physical description
    personality     TEXT,
    abilities       TEXT,       -- powers, skills, techniques
    arc_summary     TEXT,       -- narrative arc across the series
    cover_path      TEXT,       -- best panel image found of this character
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(series_id, name)
);

CREATE INDEX idx_characters_series_id ON characters(series_id);
```

```sql
-- Phase 4
-- Alternative names for a character (titles, epithets, translated names).
CREATE TABLE character_aliases (
    id              INTEGER PRIMARY KEY,
    character_id    INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    alias           TEXT    NOT NULL,
    alias_type      TEXT    NOT NULL DEFAULT 'name',
        -- 'name' | 'title' | 'epithet' | 'translation' | 'nickname'
    UNIQUE(character_id, alias)
);

CREATE INDEX idx_character_aliases_character_id ON character_aliases(character_id);
-- Used for name-based search ("find all characters named Jin-woo across series")
CREATE INDEX idx_character_aliases_alias ON character_aliases(alias);
```

```sql
-- Phase 4
-- Bidirectional relationships between characters within a series.
-- Canonical ordering: character_a_id is always less than character_b_id.
-- This prevents storing (A→B) and (B→A) as separate rows.
CREATE TABLE character_relationships (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    character_a_id  INTEGER     NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    character_b_id  INTEGER     NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    relationship_type TEXT      NOT NULL,
        -- 'ally' | 'enemy' | 'rival' | 'romantic' | 'family' | 'mentor' | 'contract' | 'unknown'
    description     TEXT,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (character_a_id != character_b_id),
    CHECK (character_a_id < character_b_id),  -- canonical ordering
    UNIQUE(character_a_id, character_b_id)
);

CREATE INDEX idx_char_rel_series   ON character_relationships(series_id);
CREATE INDEX idx_char_rel_char_a   ON character_relationships(character_a_id);
CREATE INDEX idx_char_rel_char_b   ON character_relationships(character_b_id);
```

```sql
-- Phase 3
-- Which chapters (and optionally pages) a character appears in.
-- Primary source for "find every chapter with this character" search.
CREATE TABLE character_appearances (
    id              BIGINT      PRIMARY KEY,
    character_id    INTEGER     NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    chapter_id      INTEGER     NOT NULL REFERENCES chapters(id)   ON DELETE CASCADE,
    page_id         BIGINT      REFERENCES pages(id)               ON DELETE SET NULL,
    page_number     INTEGER,
    context_note    TEXT,   -- "major fight scene" | "mentioned in dialogue"
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,

    UNIQUE(character_id, chapter_id, page_number)
);

CREATE INDEX idx_char_appearances_character ON character_appearances(character_id);
CREATE INDEX idx_char_appearances_chapter   ON character_appearances(chapter_id);
```

---

### 4.15 Timeline

```sql
-- Phase 4
-- Chronological events in the story's internal timeline.
-- sequence_order is REAL to allow inserting between existing events
-- (e.g., inserting a flashback between events 3 and 4 → sequence_order 3.5).
CREATE TABLE timeline_events (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    title           TEXT        NOT NULL,
    description     TEXT,
    event_type      TEXT        NOT NULL DEFAULT 'story',
        -- 'story' | 'flashback' | 'revelation' | 'background' | 'hypothetical'
    sequence_order  REAL        NOT NULL,   -- explicit ordering; not derived from chapter number
    chapter_id      INTEGER     REFERENCES chapters(id)          ON DELETE SET NULL,
    page_number     INTEGER,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    is_spoiler      INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_timeline_events_series ON timeline_events(series_id);
CREATE INDEX idx_timeline_events_order  ON timeline_events(series_id, sequence_order);
CREATE INDEX idx_timeline_events_chapter ON timeline_events(chapter_id);
```

```sql
-- Phase 4
-- Which characters are involved in each timeline event.
CREATE TABLE timeline_event_characters (
    timeline_event_id   INTEGER NOT NULL REFERENCES timeline_events(id) ON DELETE CASCADE,
    character_id        INTEGER NOT NULL REFERENCES characters(id)      ON DELETE CASCADE,
    role                TEXT,   -- 'actor' | 'witness' | 'mentioned' | 'victim'
    PRIMARY KEY (timeline_event_id, character_id)
);

CREATE INDEX idx_timeline_event_chars_char ON timeline_event_characters(character_id);
```

---

### 4.16 World Memory

```sql
-- Phase 4
-- Locations in the story world. Self-referencing hierarchy:
-- World → Region → City → Building → Room
CREATE TABLE world_locations (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id)          ON DELETE CASCADE,
    parent_id       INTEGER     REFERENCES world_locations(id)          ON DELETE SET NULL,
    name            TEXT        NOT NULL,
    description     TEXT,
    location_type   TEXT        NOT NULL DEFAULT 'place',
        -- 'world' | 'region' | 'city' | 'building' | 'dungeon' | 'realm' | 'place'
    first_appears_chapter_id INTEGER REFERENCES chapters(id)           ON DELETE SET NULL,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_world_locations_series ON world_locations(series_id);
CREATE INDEX idx_world_locations_parent ON world_locations(parent_id);
```

```sql
-- Phase 4
-- Organizations, guilds, nations, families. Self-referencing for sub-factions.
CREATE TABLE world_factions (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id)          ON DELETE CASCADE,
    parent_id       INTEGER     REFERENCES world_factions(id)           ON DELETE SET NULL,
    name            TEXT        NOT NULL,
    description     TEXT,
    faction_type    TEXT        NOT NULL DEFAULT 'organization',
        -- 'organization' | 'nation' | 'guild' | 'family' | 'religion' | 'group'
    alignment       TEXT        NOT NULL DEFAULT 'unknown',
        -- 'protagonist' | 'antagonist' | 'neutral' | 'unknown'
    first_appears_chapter_id INTEGER REFERENCES chapters(id)           ON DELETE SET NULL,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_world_factions_series ON world_factions(series_id);
CREATE INDEX idx_world_factions_parent ON world_factions(parent_id);
```

```sql
-- Phase 4
-- Characters belonging to factions (many-to-many).
CREATE TABLE character_factions (
    character_id    INTEGER NOT NULL REFERENCES characters(id)    ON DELETE CASCADE,
    faction_id      INTEGER NOT NULL REFERENCES world_factions(id) ON DELETE CASCADE,
    member_role     TEXT,   -- 'leader' | 'officer' | 'member' | 'ally' | 'former'
    PRIMARY KEY (character_id, faction_id)
);

CREATE INDEX idx_character_factions_faction ON character_factions(faction_id);
```

```sql
-- Phase 4
-- Power systems, rules, historical events, cultural details, and lore.
-- These are the notes an Obsidian user would write manually — AI fills them in.
CREATE TABLE world_lore (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    title           TEXT        NOT NULL,
    content         TEXT        NOT NULL,
    lore_type       TEXT        NOT NULL DEFAULT 'misc',
        -- 'power_system' | 'rule' | 'history' | 'culture' | 'technology' | 'magic' | 'misc'
    first_appears_chapter_id INTEGER REFERENCES chapters(id) ON DELETE SET NULL,
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_world_lore_series ON world_lore(series_id);
CREATE INDEX idx_world_lore_type   ON world_lore(series_id, lore_type);
```

---

### 4.17 Story Database

```sql
-- Phase 4
-- Discrete narrative events: plot points, revelations, foreshadowing, callbacks.
-- Connected to the timeline, but scene-level rather than event-level.
CREATE TABLE story_scenes (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    chapter_id      INTEGER     NOT NULL REFERENCES chapters(id) ON DELETE CASCADE,
    location_id     INTEGER     REFERENCES world_locations(id)   ON DELETE SET NULL,
    page_start      INTEGER,
    page_end        INTEGER,
    scene_type      TEXT        NOT NULL DEFAULT 'scene',
        -- 'scene' | 'revelation' | 'foreshadowing' | 'callback' | 'plot_point' | 'climax'
    title           TEXT,
    summary         TEXT        NOT NULL,
    significance    TEXT        NOT NULL DEFAULT 'minor',
        -- 'critical' | 'major' | 'moderate' | 'minor'
    is_ai_generated INTEGER     NOT NULL DEFAULT 1,
    is_user_edited  INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_story_scenes_series  ON story_scenes(series_id);
CREATE INDEX idx_story_scenes_chapter ON story_scenes(chapter_id);
CREATE INDEX idx_story_scenes_type    ON story_scenes(series_id, scene_type);
```

```sql
-- Phase 4
-- Which characters appear in each scene.
CREATE TABLE story_scene_characters (
    scene_id        INTEGER NOT NULL REFERENCES story_scenes(id) ON DELETE CASCADE,
    character_id    INTEGER NOT NULL REFERENCES characters(id)   ON DELETE CASCADE,
    PRIMARY KEY (scene_id, character_id)
);

CREATE INDEX idx_story_scene_chars_char ON story_scene_characters(character_id);
```

---

### 4.18 AI Chat

```sql
-- Phase 3
-- Per-series conversation threads. The context_chapter_id acts as a spoiler gate:
-- only content up to and including that chapter is included in the AI's context.
CREATE TABLE ai_chat_sessions (
    id                  INTEGER     PRIMARY KEY,
    series_id           INTEGER     NOT NULL REFERENCES series(id)   ON DELETE CASCADE,
    title               TEXT,           -- auto-generated from first message
    model               TEXT        NOT NULL,
    context_chapter_id  INTEGER     REFERENCES chapters(id)          ON DELETE SET NULL,
    is_archived         INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_chat_sessions_series ON ai_chat_sessions(series_id);
```

```sql
-- Phase 3
-- Individual messages within a chat session.
-- BIGINT primary key: a heavy user could have thousands of messages per series.
CREATE TABLE ai_chat_messages (
    id          BIGINT      PRIMARY KEY,
    session_id  INTEGER     NOT NULL REFERENCES ai_chat_sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,   -- 'user' | 'assistant' | 'system'
    content     TEXT        NOT NULL,
    model       TEXT,                   -- NULL for user messages
    tokens_used INTEGER,
    is_error    INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ai_chat_messages_session         ON ai_chat_messages(session_id);
CREATE INDEX idx_ai_chat_messages_session_created ON ai_chat_messages(session_id, created_at);
```

---

### 4.19 Downloads

```sql
-- Phase 6
-- Configured download source plugins (e.g., a MangaDex integration).
CREATE TABLE download_sources (
    id          INTEGER     PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    source_type TEXT        NOT NULL,   -- 'mangadex' | 'rss' | 'url' | 'custom'
    base_url    TEXT,
    config      TEXT,       -- JSON: source-specific config (rate limits, auth, etc.)
    is_active   INTEGER     NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

```sql
-- Phase 6
-- Individual download jobs. One row per chapter (or cover) download.
CREATE TABLE download_jobs (
    id                  INTEGER     PRIMARY KEY,
    source_id           INTEGER     REFERENCES download_sources(id) ON DELETE SET NULL,
    series_id           INTEGER     REFERENCES series(id)           ON DELETE SET NULL,
    url                 TEXT        NOT NULL,
    job_type            TEXT        NOT NULL DEFAULT 'chapter',
        -- 'series_meta' | 'chapter' | 'cover' | 'bulk'
    status              TEXT        NOT NULL DEFAULT 'pending',
        -- 'pending' | 'queued' | 'downloading' | 'completed' | 'failed' | 'cancelled'
    priority            INTEGER     NOT NULL DEFAULT 5,
    display_title       TEXT,       -- human-readable job title for UI
    expected_bytes      BIGINT,
    downloaded_bytes    BIGINT      NOT NULL DEFAULT 0,
    destination_path    TEXT,       -- where the file should be placed on completion
    error_message       TEXT,
    retry_count         INTEGER     NOT NULL DEFAULT 0,
    max_retries         INTEGER     NOT NULL DEFAULT 3,
    scheduled_at        TIMESTAMPTZ,    -- for rate-limited queuing
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_download_jobs_status    ON download_jobs(status, priority);
CREATE INDEX idx_download_jobs_series    ON download_jobs(series_id);
CREATE INDEX idx_download_jobs_scheduled
    ON download_jobs(scheduled_at)
    WHERE scheduled_at IS NOT NULL AND status = 'pending';
```

---

### 4.20 Settings

```sql
-- Phase 2
-- User preferences stored in the database (distinct from config/settings.json,
-- which is for system/operator configuration like AI model names and service URLs).
-- Value column is JSON-encoded; any scalar, array, or object is valid.
CREATE TABLE settings (
    key         TEXT        PRIMARY KEY,
    value       TEXT        NOT NULL,   -- JSON-encoded
    category    TEXT        NOT NULL DEFAULT 'general',
        -- 'reader' | 'library' | 'ai' | 'ui' | 'general'
    description TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Default rows inserted on first run:
--
-- reader.default_mode           "webtoon"
-- reader.zoom_level             1.0
-- reader.prefetch_pages         10
-- reader.reading_direction      "ltr"    (ltr | rtl)
-- reader.double_page_mode       false
--
-- library.default_sort          "last_read"  (title|last_read|date_added|author|status)
-- library.default_filter        "all"        (all|reading|completed|on_hold|unread)
-- library.grid_columns          6
--
-- ai.auto_ocr_on_import         false
-- ai.auto_embed_after_ocr       true
-- ai.auto_summarize_after_embed false
-- ai.spoiler_gate_enabled       true
--
-- ui.sidebar_collapsed          false
-- ui.controls_opacity           0.8
-- ui.show_chapter_titles        true
```

---

### 4.21 Multi-User Support (Phase 6)

```sql
-- Phase 6
-- Added when NAS multi-user deployment is enabled.
-- In Phases 2–5 the app runs in single-user mode with no auth required.
CREATE TABLE users (
    id              INTEGER     PRIMARY KEY,
    username        TEXT        NOT NULL UNIQUE,
    email           TEXT        UNIQUE,
    password_hash   TEXT        NOT NULL,   -- argon2id hash
    display_name    TEXT,
    role            TEXT        NOT NULL DEFAULT 'user',
        -- 'admin' | 'user' | 'readonly'
    is_active       INTEGER     NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at   TIMESTAMPTZ
);
```

```sql
-- Phase 6
-- JWT refresh token session store. Access tokens are short-lived (15 min) and
-- not stored; only refresh tokens (30 days) are stored here.
CREATE TABLE user_sessions (
    id          INTEGER     PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT        NOT NULL UNIQUE,    -- SHA-256 of the refresh token
    device_name TEXT,
    ip_address  TEXT,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_sessions_user    ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token   ON user_sessions(token_hash);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);
```

**Phase 6 migration:** add `user_id INTEGER REFERENCES users(id) ON DELETE CASCADE`
to `reading_progress`, `chapter_progress`, `reading_sessions`, `bookmarks`,
`ai_chat_sessions`, and `settings`. Drop the UNIQUE constraints that currently assume
single-user, replace with composite UNIQUE including `user_id`.

---

### 4.22 Creation Studio (Phase 5)

```sql
-- Phase 5
-- A creation project workspace. Links to a series in the library once exported.
CREATE TABLE creation_projects (
    id              INTEGER     PRIMARY KEY,
    series_id       INTEGER     REFERENCES series(id) ON DELETE SET NULL, -- set after export
    title           TEXT        NOT NULL,
    genre           TEXT,
    format          TEXT        NOT NULL DEFAULT 'manhwa',
        -- 'manhwa' | 'manga' | 'manhua'
    synopsis        TEXT,
    target_audience TEXT,
    cover_path      TEXT,
    status          TEXT        NOT NULL DEFAULT 'draft',
        -- 'draft' | 'in_progress' | 'exported' | 'archived'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

```sql
-- Phase 5
-- Characters created for a project. Separate from library characters
-- (library characters are extracted from existing content; project characters
-- are designed by the creator).
CREATE TABLE project_characters (
    id              INTEGER     PRIMARY KEY,
    project_id      INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    name            TEXT        NOT NULL,
    role            TEXT        NOT NULL DEFAULT 'supporting',
    description     TEXT,
    appearance      TEXT,
    personality     TEXT,
    voice_style     TEXT,       -- writing style for AI character dialogue generation
    reference_prompt TEXT,      -- ComfyUI prompt for generating this character
    cover_path      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(project_id, name)
);

CREATE INDEX idx_project_characters_project ON project_characters(project_id);
```

```sql
-- Phase 5
-- Chapter units within a creation project.
CREATE TABLE project_chapters (
    id              INTEGER     PRIMARY KEY,
    project_id      INTEGER     NOT NULL REFERENCES creation_projects(id) ON DELETE CASCADE,
    chapter_number  REAL        NOT NULL,
    title           TEXT,
    synopsis        TEXT,
    status          TEXT        NOT NULL DEFAULT 'planned',
        -- 'planned' | 'scripting' | 'paneling' | 'complete' | 'exported'
    sort_order      INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(project_id, chapter_number)
);

CREATE INDEX idx_project_chapters_project ON project_chapters(project_id);
```

```sql
-- Phase 5
-- Saved ComfyUI workflow templates for image generation.
CREATE TABLE comfyui_workflows (
    id              INTEGER     PRIMARY KEY,
    name            TEXT        NOT NULL UNIQUE,
    description     TEXT,
    workflow_json   TEXT        NOT NULL,   -- full ComfyUI API JSON
    preview_path    TEXT,
    is_default      INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

```sql
-- Phase 5
-- AI-generated images produced by ComfyUI.
CREATE TABLE generated_assets (
    id              INTEGER     PRIMARY KEY,
    project_id      INTEGER     NOT NULL REFERENCES creation_projects(id)   ON DELETE CASCADE,
    chapter_id      INTEGER     REFERENCES project_chapters(id)             ON DELETE SET NULL,
    character_id    INTEGER     REFERENCES project_characters(id)           ON DELETE SET NULL,
    asset_type      TEXT        NOT NULL DEFAULT 'panel',
        -- 'panel' | 'character_ref' | 'background' | 'mood_board' | 'cover'
    file_path       TEXT        NOT NULL,   -- absolute path under generated/
    prompt          TEXT,
    negative_prompt TEXT,
    model           TEXT,
    workflow_id     INTEGER     REFERENCES comfyui_workflows(id)            ON DELETE SET NULL,
    seed            BIGINT,
    width           INTEGER,
    height          INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_generated_assets_project   ON generated_assets(project_id);
CREATE INDEX idx_generated_assets_chapter   ON generated_assets(chapter_id);
CREATE INDEX idx_generated_assets_character ON generated_assets(character_id);
```

```sql
-- Phase 5
-- Individual panels within a project chapter.
-- generated_asset_id is a plain INTEGER (not a FK) to avoid the circular FK
-- between project_panels and generated_assets.
-- Relationship is navigated via generated_assets WHERE chapter_id = this chapter_id.
CREATE TABLE project_panels (
    id                  INTEGER     PRIMARY KEY,
    chapter_id          INTEGER     NOT NULL REFERENCES project_chapters(id) ON DELETE CASCADE,
    panel_number        INTEGER     NOT NULL,
    layout_type         TEXT        NOT NULL DEFAULT 'full',
        -- 'full' | 'half_horizontal' | 'half_vertical' | 'quarter' | 'custom'
    dialogue            TEXT,
    narration           TEXT,
    action_description  TEXT,       -- direction notes for the image prompt
    comfyui_prompt      TEXT,
    generated_asset_id  INTEGER,    -- references generated_assets(id); not a FK (circular)
    status              TEXT        NOT NULL DEFAULT 'empty',
        -- 'empty' | 'scripted' | 'prompted' | 'generated' | 'approved'
    sort_order          INTEGER     NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(chapter_id, panel_number)
);

CREATE INDEX idx_project_panels_chapter ON project_panels(chapter_id);
```

---

## 5. Index Strategy Summary

### Indexing rules applied throughout this schema

1. **Every foreign key column has an index.** SQLite (unlike PostgreSQL) does not
   automatically index FK columns. Missing FK indexes cause full table scans on
   cascaded deletes and join queries.

2. **Sort columns are indexed with the correct sort direction.** `last_read_at DESC`
   on `reading_progress` is a covering index for the "continue reading" query.
   Without the DESC, the query must scan and reverse-sort at query time.

3. **Partial indexes reduce index size on sparse predicates.**
   - `WHERE deleted_at IS NULL` on series (most rows are live)
   - `WHERE status = 'pending'` on task queues (most tasks are completed)
   - `WHERE is_favorite = 1` on series (minority of rows)

4. **BIGINT primary keys on high-cardinality tables.** Standard `INTEGER` in SQLite
   is 64-bit (signed), so this is a documentation convention for SQLAlchemy to emit
   the correct type declaration on PostgreSQL (`BIGINT`).

5. **Composite indexes match query patterns exactly.**
   - `(series_id, sort_key)` on chapters: the exact columns in the read-order query.
   - `(task_type, status)` on background_tasks: task workers filter on both.
   - `(series_id, sequence_order)` on timeline_events: timeline tab query.
   - `(session_id, created_at)` on ai_chat_messages: conversation loading.

6. **FTS5 content tables use external content mode** (`content='table'`,
   `content_rowid='id'`). This avoids duplicating text storage but requires the
   three triggers per table to stay in sync. The triggers are defined above alongside
   each FTS table.

### Tables without additional indexes

| Table | Reason |
|-------|--------|
| `settings` | PK-only lookup by key string; < 100 rows ever |
| `libraries` | < 50 rows; full scan is faster than index overhead |
| `volumes` | Low cardinality; UNIQUE index on (series_id, number) is sufficient |
| `collections` | < 500 rows typical; UNIQUE on name is sufficient |
| `tags` | < 1,000 rows; UNIQUE on name is sufficient |
| `comfyui_workflows` | < 100 rows; UNIQUE on name is sufficient |

---

## 6. Scale Analysis

At the stated targets (100,000 chapters, millions of pages):

| Table | Expected rows | PK type | Dominant index |
|-------|--------------|---------|---------------|
| `series` | 10,000–50,000 | INTEGER | `idx_series_live` (sort by sort_title, filter deleted_at) |
| `volumes` | 50,000–200,000 | INTEGER | `idx_volumes_series_id` |
| `chapters` | 100,000–500,000 | INTEGER | `idx_chapters_series_sort` |
| `pages` | 5,000,000–20,000,000 | **BIGINT** | `idx_pages_chapter_id` |
| `ocr_pages` | 0–10,000,000 | **BIGINT** | `idx_ocr_pages_page_id` |
| `embedding_chunks` | 0–20,000,000 | **BIGINT** | `idx_embedding_chunks_source` |
| `embeddings` | 0–20,000,000 | **BIGINT** | `idx_embeddings_model` |
| `character_appearances` | 0–5,000,000 | **BIGINT** | `idx_char_appearances_character` |
| `ai_chat_messages` | 0–1,000,000 | **BIGINT** | `idx_ai_chat_messages_session_created` |
| `reading_sessions` | 0–500,000 | **BIGINT** | `idx_reading_sessions_started` |

### SQLite limits at this scale

SQLite handles this scale comfortably in WAL mode with the following caveats:

- **Embeddings at 10M rows × 3KB = 30GB.** This is a single BLOB column and will
  make the database file very large. SQLite performs poorly at database files above
  ~10GB on spinning disk. At this scale, migrate embeddings to PostgreSQL with
  `pgvector`, or use a dedicated vector database (Chroma, Qdrant).
- **OCR_FTS index size.** FTS5 maintains its own B-tree; at 10M OCR pages it will
  be 5–15GB additional storage. Acceptable on SSD; add `fts5_automerge` configuration
  for write-heavy OCR workers.
- **WAL mode** must be set on every connection. WAL allows concurrent reads during
  background worker writes — critical for a responsive UI during scanning.

### PostgreSQL migration triggers

Migrate from SQLite to PostgreSQL when any of these thresholds are hit:
- Database file exceeds 8GB.
- Library page load (10K+ series) exceeds 500ms with proper indexes in place.
- Concurrent background workers cause WAL contention.
- Multi-user (Phase 6) is enabled — PostgreSQL's row-level locking is required.

---

## 7. Initialization Sequence

On first startup, the backend creates tables in this order (respects FK dependencies):

```
1.  libraries
2.  series                  (FK → libraries)
3.  volumes                 (FK → series)
4.  chapters                (FK → series, volumes)
5.  pages                   (FK → chapters)
6.  reading_progress        (FK → series, chapters)
7.  chapter_progress        (FK → chapters)
8.  reading_sessions        (FK → series, chapters)
9.  bookmarks               (FK → series, chapters, pages)
10. collections
11. collection_series       (FK → collections, series)
12. tags
13. series_tags             (FK → series, tags)
14. import_history          (FK → libraries)
15. background_tasks
16. settings
17. ai_summaries            (FK → series, chapters)
18. ocr_pages               (FK → pages)
19. chapter_ocr_status      (FK → chapters)
20. series_ai_status        (FK → series)
21. embedding_chunks        (FK → series)
22. embeddings              (FK → embedding_chunks)
23. characters              (FK → series)
24. character_aliases       (FK → characters)
25. character_relationships (FK → series, characters)
26. character_appearances   (FK → characters, chapters, pages)
27. timeline_events         (FK → series, chapters)
28. timeline_event_chars    (FK → timeline_events, characters)
29. world_locations         (FK → series, chapters, self)
30. world_factions          (FK → series, chapters, self)
31. character_factions      (FK → characters, world_factions)
32. world_lore              (FK → series, chapters)
33. story_scenes            (FK → series, chapters, world_locations)
34. story_scene_characters  (FK → story_scenes, characters)
35. ai_chat_sessions        (FK → series, chapters)
36. ai_chat_messages        (FK → ai_chat_sessions)
37. download_sources
38. download_jobs           (FK → download_sources, series)
39. -- FTS5 virtual tables (no FK dependencies, but require source tables):
40. series_fts              (mirrors series)
41. ocr_fts                 (mirrors ocr_pages)
42. summary_fts             (mirrors ai_summaries)
43. -- Phase 5:
44. creation_projects       (FK → series)
45. project_characters      (FK → creation_projects)
46. project_chapters        (FK → creation_projects)
47. comfyui_workflows
48. generated_assets        (FK → creation_projects, project_chapters, project_characters, comfyui_workflows)
49. project_panels          (FK → project_chapters)
50. -- Phase 6:
51. users
52. user_sessions           (FK → users)
```

All tables are created by Alembic migrations. Table creation order is Alembic's
responsibility; this list is the logical order for understanding dependencies.

---

## 8. Alembic Migration Policy

- Every schema change — add column, add table, add index — requires an Alembic migration.
- No `CREATE TABLE` or `ALTER TABLE` in application startup code.
- Migrations are additive where possible (add columns, add tables).
- Breaking changes (drop column, rename column) require a data-preservation plan
  documented in the migration file header comment.
- No migration deletes user data without an explicit backup step.
- FTS5 virtual tables are created in migrations, not in SQLAlchemy models.
  They do not have corresponding ORM classes.
