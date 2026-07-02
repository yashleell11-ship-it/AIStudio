# AIStudio — Development Roadmap

One phase at a time. Each phase delivers something real. Never start the next phase
until the current one builds clean, type-checks clean, and the feature is actually usable.

---

## Phase 1 — Foundation ✅ Complete

**Goal:** A skeleton that every future feature builds on. Nothing for users to use yet, but
an architecture they'll never need to fight.

**Delivered:**
- Feature-based `frontend/src/` structure — one organizing principle, no duplication.
- Design system: forced dark theme, Tailwind v4 `@theme` design tokens, `cn()` helper, `Button` primitive.
- App shell: collapsible sidebar, topbar, responsive layout.
- Nav structure: Library, Reader, Create, Search, AI, Settings (route placeholders).
- Keyboard shortcut layer: typed registry, one global listener, `useShortcut` hook.
  First shortcut: `Ctrl/Cmd+B` toggles sidebar.
- Typed API client (`services/http.ts`): one `fetch` wrapper, `ApiError`, typed responses.
- State management: TanStack Query (server state) + Zustand (UI state) wired via `Providers`.
- Backend clean architecture: `routes/ → services/ → core/`; `create_app()` factory;
  settings loader reading `config/settings.json`; uniform error envelope; CORS.
- `requirements.txt`, `docs/STRUCTURE.md`.

**Architecture decision:** No feature code in Phase 1. Foundation must be stable before
any pillar is built on it.

---

## Phase 2 — Library + Reader

**Goal:** A real user can point the app at their manhwa folder and start reading.
This is the core vertical slice that proves the entire stack.

### 2a — Backend: Library scanner + data layer

**Database:** Migrate `backend/database.py` to `backend/database/` package:
- `models.py`: SQLAlchemy 2.x declarative models (Series, Volume, Chapter, Page,
  ReadingProgress, Library, ImportHistory, Collection, Tag, Bookmark).
- `session.py`: session factory with `PRAGMA foreign_keys = ON`.
- `migrations/`: Alembic setup for future schema changes.

**Services** (`backend/services/library_service.py`):
- `scan_library(root_path)` — recursive walk; auto-detect series/chapter/page hierarchy.
- `import_folder(folder_path)` — upsert series/chapters/pages; never copy files.
- `list_series(sort, filter)` — paginated series list.
- `get_series(id)` — series detail with chapter list.
- `get_chapter(id)` — chapter detail with ordered page list.
- `get_page_image(page_id)` — resolve file path, return image.

**Background:** `workers/scanner.py`:
- Non-blocking scan triggered on startup and by manual API call.
- Progress streamed via WebSocket (`/ws/scan-progress`).

**Thumbnail generator** (`workers/thumbnailer.py`):
- Generates `covers/<series_id>/<chapter_id>.jpg` from first page.
- Runs after scan, batch, background.

**Routes** (`backend/routes/library.py`):
- `GET /library/series` — paginated list.
- `GET /library/series/{id}` — detail + chapters.
- `GET /library/chapters/{id}` — detail + pages.
- `GET /library/pages/{id}/image` — serve image file.
- `POST /library/import` — start background scan.
- `GET /library/scan-status` — poll scan progress (WebSocket later).
- `GET /library/covers/{series_id}` — serve cover image.

**Supported formats (Phase 2):**
- Image folders (JPG, PNG, WEBP) — this is the primary format.
- CBZ/ZIP — streaming extraction, no temp copies.
- PDF — deferred to Phase 2b.

**Acceptance criteria:**
- `POST /library/import` with a real local path returns success without copying files.
- `GET /library/series` returns the imported series in < 200ms for a 500-series library.
- Covers appear for imported series.
- All endpoints match the error envelope contract.

---

### 2b — Frontend: Library feature module

**`features/library/`:**
- `api.ts`: typed calls to all library routes using `services/http.ts`.
- `hooks.ts`: `useSeriesList()`, `useSeries()`, `useChapter()` — TanStack Query wrappers.
- `types.ts`: `Series`, `Chapter`, `Page`, `ReadingProgress` matching backend Pydantic models.
- `components/`:
  - `SeriesGrid.tsx` — responsive grid, virtual scroll at large sizes.
  - `SeriesCard.tsx` — cover + title + chapter count + continue reading badge.
  - `SeriesDetail.tsx` — chapter list, metadata, reading stats.
  - `ImportDialog.tsx` — folder path input, progress display.

**Library page** (`app/library/page.tsx`):
- Server Component: fetches initial series list.
- Client Components for interaction: search, sort, filter, import.
- Keyboard shortcuts: `/` to focus search, `i` to open import dialog.
- Empty state: helpful prompt to import a library.

**Design:** uses design tokens (no hardcoded colors), matches the dark theme.

**Acceptance criteria:**
- User imports a real local folder and sees their series in the grid.
- Grid shows covers, titles, chapter counts.
- Search and sort work client-side without new API calls.
- Keyboard shortcuts work.
- Builds and type-checks clean.

---

### 2c — Backend: Image serving + Reader API

**Routes** (`backend/routes/reader.py`):
- `GET /reader/chapter/{id}` — ordered pages with metadata.
- `GET /reader/page/{id}/image` — serve image with proper `Content-Type`, `Cache-Control`.
- `POST /reader/progress` — save `{chapter_id, last_page}`.
- `GET /reader/progress/{series_id}` — resume data.

**Image serving:**
- `FileResponse` with long `Cache-Control` for local images.
- `StreamingResponse` for CBZ pages (decompress on the fly).
- Always validate path is within a registered library root (no path traversal).

---

### 2d — Frontend: Reader feature module

**`features/reader/`:**
- `components/`:
  - `WebtoonReader.tsx` — vertical scroll, full-width images, lazy loading per image.
  - `MangaReader.tsx` — single/double page, left-to-right and right-to-left.
  - `ReaderControls.tsx` — overlaid toolbar: mode switch, zoom, progress, shortcuts.
  - `PageImage.tsx` — progressive loading, blur-up placeholder, error state.
- Keyboard shortcuts: arrow keys / `j`/`k` to navigate; `m` to switch mode; `b` to bookmark; `Esc` to exit.
- Auto-save reading progress every N pages.

**Acceptance criteria:**
- User clicks a series in the Library, lands in the Reader.
- Webtoon mode scrolls smoothly through all pages.
- Progress is saved and "Continue Reading" works on next visit.
- Builds and type-checks clean.

---

## Phase 3 — AI Layer

**Goal:** Every imported series becomes queryable. Users can ask questions, get summaries,
and search by meaning. All local. No cloud.

### 3a — OCR pipeline
- Vision model via Ollama (e.g. `minicpm-v`) extracts text from panel images.
- Background queue processes pages post-import; progress visible in UI.
- Extracted text stored in `ocr_pages` table indexed for FTS5.
- Dialogue search available immediately after OCR.

### 3b — Summarization
- Chapter summaries generated by `default_writer` model.
- Series overview generated from chapter summaries.
- Stored in `ai_summaries`; regeneratable.

### 3c — Semantic search
- `default_embedder` model embeds text chunks (OCR + summaries).
- Stored as byte blobs; cosine similarity search in Python (numpy).
- Phase 5: upgrade to `pgvector` when PostgreSQL migration happens.

### 3d — AI chat
- Series-scoped Q&A: user asks, backend assembles context (OCR + summaries + character data), asks Ollama, streams response.
- Chat history stored per session.
- Frontend: streaming chat UI in the AI pillar.

### 3e — Automatic metadata
- Extract character names from OCR text.
- Classify genre and tags.
- Generate series description.
- All results editable by the user.

---

## Phase 4 — Knowledge Graph

**Goal:** AIStudio becomes an Obsidian for manhwa. Every character, location, and event
is tracked and linked.

- **Character profiles:** name, aliases, traits, relationships, arc summary, cover image.
- **Relationship graph:** interactive D3/canvas visualization of character connections.
- **World builder:** locations, factions, power systems, lore entries.
- **Timeline:** chronological event list extracted from summaries + user-editable.
- **Story database:** scenes, revelations, foreshadowing, callbacks.
- All data is bidirectionally linked: chapter → character → scene → location.

---

## Phase 5 — Creation Studio

**Goal:** Users can create their own manhwa inside the same application they use to read.

- Project workspace: character sheets, world bible, chapter outlines.
- Panel planning: script text → storyboard layout with panel grid.
- Image generation: ComfyUI integration, local diffusion models.
  Text-to-panel, character reference injection, inpainting.
- Reference manager: mood boards, character reference images.
- Asset library: reuse generated images across panels.
- Export: CBZ, PDF, image folder.
- The created series appears directly in the Library.

---

## Phase 6 — Advanced features

**Goal:** Power users and NAS deployments.

- **Download manager:** queue, retry, resume; automatic organization; metadata fetch.
- **Multi-library:** multiple root paths; separate library views.
- **Reading statistics:** charts, streaks, time spent, pages per day.
- **Multi-user (NAS):** JWT auth, per-user reading progress, shared library.
- **Mobile web:** responsive reader optimized for touch; PWA manifest.
- **Plugins:** documented extension API; community themes and sources.
- **Cloud sync (optional):** reading progress only; content stays local.

---

## Recurring rules (every phase)

These apply to every phase, enforced before declaring a phase complete:

1. **Builds clean:** `npm run build` in `frontend/` passes with zero errors.
2. **Type-checks clean:** `npx tsc --noEmit` passes with zero errors.
3. **No placeholder code:** every implemented function does real work.
4. **No TODO comments** in committed code.
5. **Architecture review:** no regressions in the layer separation.
6. **Structure review:** `docs/STRUCTURE.md` updated to reflect new files.
7. **Error contract:** all new endpoints return the standard error envelope.
8. **Design tokens:** no hardcoded colors — only `var(--color-*)` or Tailwind token classes.
9. **Keyboard coverage:** every new interactive feature has at least its primary shortcut.

---

## What Phase 2 requires before it starts

The following issues in the external edits to `backend/` need to be resolved first:

- `backend/main.py` uses relative imports (`.database`) which require `__init__.py` at the backend level — the current backend is not a Python package. The imports must be absolute (matching Phase 1 architecture) or the package structure must be updated.
- `backend/database.py` uses `declarative_base()` (deprecated in SQLAlchemy 2.x) and references `relationship` and `Table` without importing them. It also references back-populates that don't exist on the target models.
- `backend/api/library.py` imports `PIL` (Pillow) which is not installed; imports from `.database` using a broken relative path; and places business logic (file walking, cover generation) directly in the route — violating the architecture rule.
- `frontend/src/app/library/page.tsx` uses `useState` and `useEffect` in a Server Component (missing `'use client'`), uses hardcoded light-theme classes instead of design tokens, and bypasses TanStack Query.

These will be fixed at the start of Phase 2 implementation as the first task.
