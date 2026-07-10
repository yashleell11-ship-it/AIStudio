# AIStudio — Technical Architecture

## Overview

AIStudio is two cooperating applications: a **Next.js 16 frontend** that owns the UI, and a **FastAPI backend** that owns data, files, and AI. They communicate over HTTP. The frontend is the single consumer of the API — there is no direct database access or file I/O in the frontend.

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (Next.js)                     │
│  AppShell → Features → TanStack Query → services/http   │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP / JSON
┌───────────────────────▼─────────────────────────────────┐
│                 FastAPI (Python)                          │
│  routes/ → services/ → database/ ← background workers   │
│               core/ (config, errors)                     │
└──────┬────────────────┬───────────────┬─────────────────┘
       │                │               │
   SQLite DB      Local files      Ollama / ComfyUI
   (→ Postgres)   (images, covers,  (AI models)
                  archives)
```

---

## Frontend architecture

### Layer responsibilities

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Routes | `app/<route>/page.tsx` | Thin — fetch data, delegate to feature module |
| Feature modules | `features/<name>/` | All logic, components, and hooks for one pillar |
| Shared UI | `components/ui/` | Primitives: Button, Input, Card, Badge, etc. |
| Shell | `components/layout/` | AppShell, Sidebar, Topbar — cross-cutting chrome |
| API client | `services/http.ts` | One typed `fetch` wrapper used by every feature service |
| Feature services | `features/<name>/api.ts` or `services/<name>.ts` | Feature-specific API calls |
| Server state | TanStack Query | Fetching, caching, mutations, background refetch |
| Client state | Zustand (`stores/`) | UI state: sidebar collapse, reader mode, shortcuts |
| Keyboard | `lib/keyboard/` | Central registry; one listener; `useShortcut` hook |
| Utilities | `lib/` | `cn()` and other framework-agnostic helpers |
| Types | `types/` | Shared domain types matching the API response shapes |
| Config | `config/` | `env.ts` (runtime env), `nav.ts` (nav structure) |

### Server vs. Client Components

- Route pages are **Server Components** by default (no state, no hooks, no `useEffect`).
- Interactive components within a feature are **Client Components** (`'use client'`).
- Providers (`Providers`, `KeyboardProvider`) are Client Components wrapping `{children}` — never the `<html>` tag.
- The rule: push `'use client'` as deep as possible to minimize JS bundle size.

### State ownership

```
Server state (from the API)      → TanStack Query
 examples: library items, chapter pages, reading progress

Client/UI state (browser-only)   → Zustand
 examples: sidebar open/closed, reader scroll mode, active modal
```

Never put server data into Zustand. Never put UI state into TanStack Query.

### Feature module structure

Each pillar is a self-contained module:

```
features/library/
├─ api.ts          FastAPI calls for this feature (uses services/http.ts)
├─ hooks.ts        useQuery / useMutation wrappers
├─ types.ts        Feature-specific types
├─ components/     UI components private to this feature
└─ index.ts        Public surface (re-export what routes/other features need)
```

---

## Backend architecture

### Layer responsibilities

```
Routes  →  Services  →  Database / AI clients
  ↑              ↑
  HTTP         Business logic
  shape        (no SQLAlchemy in routes)
```

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Entry | `main.py` | `create_app()` factory; mounts CORS, error handlers, router |
| Router | `api/router.py` | Aggregates all route modules |
| Routes | `routes/<feature>.py` | HTTP shape: parse input, call service, return output |
| Services | `services/<name>.py` | Business logic, orchestration, no HTTP concerns |
| Database | `database/` | Models, session factory, migrations |
| Background | `workers/` | Long-running tasks (scanner, OCR queue, thumbnail gen) |
| AI | `services/ollama_service.py`, `services/ocr_service.py`, etc. | AI client wrappers |
| Core | `core/config.py`, `core/errors.py` | Config loading, error envelope |

**Rule:** Business logic never lives in a route. Routes are thin.

### Error contract

Every error response — validation, not-found, AI unavailable, unexpected — returns exactly:

```json
{
  "code": "machine_readable_code",
  "message": "Human readable message.",
  "details": { ... }
}
```

`details` is optional. The frontend's `ApiError` class in `types/api.ts` parses this shape. Never break this contract.

### Dependency injection

Services are FastAPI `Depends()` singletons created by a factory function decorated with `@lru_cache`. They are instantiated once per process, never per-request:

```python
# services/library_service.py
@lru_cache
def get_library_service() -> LibraryService:
    return LibraryService(db_path=get_settings().db_path)

# routes/library.py
@router.get("/library")
def get_library(service: Annotated[LibraryService, Depends(get_library_service)]):
    return service.list_all()
```

### Configuration

`core/config.py` reads `config/settings.json` at the repo root. All service URLs, model defaults, and paths come from there. Routes and services access config via `get_settings()` — never via `os.environ` directly.

---

## Database architecture

### Schema design goals

- Normalized — no duplicated data.
- All entities have integer primary keys.
- Foreign keys enforced (SQLite with `PRAGMA foreign_keys = ON`).
- Designed for PostgreSQL from day one: no SQLite-isms in queries.

### Core schema (SQLite → PostgreSQL)

```
series
  id, title, author, description, status, cover_path
  year, language, content_rating
  created_at, updated_at

volumes
  id, series_id (FK), title, number, cover_path

chapters
  id, series_id (FK), volume_id (FK nullable)
  title, number, folder_path, archive_path
  page_count, cover_path
  created_at, scanned_at

pages
  id, chapter_id (FK), number, file_path, width, height

reading_progress
  id, series_id (FK), chapter_id (FK), last_page
  progress_pct, started_at, last_read_at

libraries (multiple root folders)
  id, name, root_path, scan_interval_minutes, created_at

import_history
  id, library_id (FK), folder_path, status
  series_count, chapter_count, page_count, started_at, finished_at

collections
  id, name, description, cover_path, created_at

collection_series   (many-to-many)
  collection_id (FK), series_id (FK)

tags
  id, name (unique)

series_tags         (many-to-many)
  series_id (FK), tag_id (FK)

bookmarks
  id, series_id (FK), chapter_id (FK), page, note, created_at

-- AI layer (Phase 3+)
ai_summaries
  id, series_id (FK), chapter_id (FK nullable)
  model, content, created_at

characters
  id, series_id (FK), name, aliases, description, cover_path, created_at

character_appearances
  id, character_id (FK), chapter_id (FK), page, note

ocr_pages
  id, page_id (FK), text_content, model, created_at

embeddings
  id, source_type, source_id, model, vector (BLOB / pgvector later)
```

### PostgreSQL migration path

When migrating from SQLite to PostgreSQL:
1. All query code uses SQLAlchemy Core/ORM — no raw SQL dialects.
2. The connection string is the only change in `config/settings.json`.
3. `BLOB` embeddings upgrade to `pgvector` extension via a single column type swap.
4. No application logic changes.

---

## File system architecture

### How files are stored

AIStudio never moves or copies original files. It indexes them where they are.

```
User's library folder (anywhere on disk):
├─ Solo Leveling/
│  ├─ Chapter 001/
│  │  ├─ 001.jpg
│  │  └─ 002.jpg
│  └─ Chapter 002 - The Boss/
│     └─ ...
├─ Tower of God [CBZ]/
│  ├─ ToG_001.cbz
│  └─ ToG_002.cbz
└─ Berserk.pdf

AIStudio internal storage (D:/AIStudio/):
├─ covers/      Generated thumbnails (never originals)
├─ generated/   AI-generated images (ComfyUI output)
├─ exports/     User exports (CBZ, PDF)
└─ ai_studio.db
```

### Supported formats

| Format | How it's handled |
|--------|-----------------|
| Image folders | Walk directory, sort files numerically |
| CBZ / ZIP | Extract on read (streaming), no copy |
| CBR / RAR | Extract on read (streaming), no copy |
| PDF | Page-by-page render on demand |

---

## Background services

Long-running operations run as background tasks, never blocking the API.

| Service | Trigger | What it does |
|---------|---------|--------------|
| Library scanner | Startup, folder watch, manual | Walk registered library paths; upsert series/chapters/pages |
| Folder watcher | Startup | `watchdog` on library root paths; triggers incremental scan on change |
| Thumbnail generator | Post-scan | Generate covers for new chapters/series (first page → resize) |
| OCR queue | Post-scan or manual | Run Ollama vision model over page images; store text in `ocr_pages` |
| Embedding queue | Post-OCR / post-summary | Run embedding model over text; store in `embeddings` |
| AI summary queue | Manual or scheduled | Summarize chapter/series via Ollama; store in `ai_summaries` |

Queues use FastAPI's `BackgroundTasks` initially. At scale (Phase 5+) they will migrate to a task queue (Celery or ARQ + Redis, or a simpler SQLite-backed queue).

---

## AI architecture

All AI runs locally via Ollama. Model selection is per-task and user-configurable.

```
config/settings.json:
  default_chat: qwen3:30b         # General Q&A, character chat
  default_writer: llama3.3:70b    # Summaries, descriptions
  default_reasoner: deepseek-r1:32b  # Complex reasoning, timeline
  default_vision: minicpm-v:8b    # OCR, panel analysis
  default_embedder: nomic-embed-text  # Embeddings for semantic search
```

### AI pipeline for a newly imported series

```
1. Scanner → pages in DB
2. Thumbnail generator → covers in covers/
3. OCR queue → text per page in ocr_pages
4. Embedding queue → text chunks embedded → vectors in embeddings
5. Summary queue → chapter summaries → ai_summaries
6. Character extractor → character names → characters
7. Index updated → series searchable semantically
```

Steps 3–7 are optional and happen asynchronously. The user can read immediately after step 1.

---

## Performance targets

| Scenario | Target |
|----------|--------|
| Library page load (10,000 series) | < 200ms |
| Reader: next chapter page | < 50ms |
| Search results | < 100ms |
| Thumbnail generation | Non-blocking; batch in background |
| Background scan (10,000 chapters) | Must not block the UI |
| OCR (single chapter, 80 pages) | Queued, progress reported via WebSocket |
| Embedding generation | Batched, runs when AI is idle |

### Techniques

- Database: indexed queries on `series_id`, `chapter_id`, `folder_path`.
- Images: served by FastAPI as `FileResponse` with `Cache-Control` headers.
- Reader: prefetch next chapter while reading current.
- Library grid: virtual scrolling (TanStack Virtual) at large library sizes.
- Search: FTS5 (SQLite full-text search) for text; vector similarity for semantic.

---

## Security model

- The backend binds to `127.0.0.1` only. Not accessible from LAN by default.
- CORS allows only the configured frontend origin.
- No authentication for single-user mode. Multi-user adds JWT + session layer later.
- File paths from the user are validated to be inside registered library root paths (path traversal prevention).
- AI model names from the user are validated against the Ollama API's model list.

---

## Technology choices and rationale

| Choice | Alternative considered | Why this |
|--------|----------------------|----------|
| Next.js 16 App Router | Remix, SvelteKit | Largest ecosystem for RSC; best TypeScript support |
| Tailwind v4 | v3, CSS Modules | v4's `@theme` CSS variables are what we need for the design token system |
| TanStack Query | SWR, React Query v3 | v5 has the best TypeScript generics; mutation UX is cleanest |
| Zustand | Jotai, Redux | Minimal boilerplate; selector-based subscriptions |
| FastAPI | Django REST, Flask | Auto-generates OpenAPI spec; Pydantic types; async native |
| SQLAlchemy | Raw SQL, Tortoise | Supports both SQLite and PostgreSQL; migration to Postgres is a config change |
| Ollama | HuggingFace local, llama.cpp direct | Best Windows support; model library; HTTP API compatible with OpenAI SDK |
| ComfyUI | A1111, InvokeAI | Node-based workflow; API-first; best for programmatic generation |
