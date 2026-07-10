# Project Structure

_Phase 1 built. Phase 2 in progress. This document shows both current state and
intended full-scale layout — new paths are marked (Phase N) when not yet created._

---

## Repository root

```
AIStudio/
├─ frontend/        Next.js 16 + React 19 + Tailwind v4
├─ backend/         FastAPI + SQLAlchemy + Ollama orchestration
├─ config/
│  └─ settings.json Shared runtime config read by the backend on startup
├─ memory/          Creation studio domain data (characters, world, timeline, …)
├─ projects/        User-created manhwa projects (ManhwaStudio/)
├─ covers/          Generated series/chapter thumbnails (created at runtime)
├─ exports/         User-exported files (CBZ, PDF)
├─ generated/       AI-generated images (ComfyUI output)
├─ docs/
│  ├─ VISION.md         Product vision and long-term goals
│  ├─ PRODUCT.md        Full PRD — audience, personas, screens, workflows
│  ├─ PROJECT_RULES.md  Permanent rulebook — architecture, coding, process
│  ├─ ARCHITECTURE.md   Technical decisions, patterns, data flow
│  ├─ DATABASE.md       Complete production database schema (all 50 tables)
│  ├─ API.md            Complete REST API contract — every endpoint, request, response, error
│  ├─ AI_PIPELINE.md   Complete AI pipeline design — all 18 stages, GPU usage, scale path
│  ├─ CREATION_STUDIO.md  Creation Studio full architecture — 9 components, data model, consistency system
│  ├─ ROADMAP.md        Phase-by-phase development plan
│  ├─ STRUCTURE.md      This file
│  └─ CONTRIBUTING.md   Contribution guide — standards, workflow, review
└─ ai/ assets/ prompts/ scripts/ templates/ workflows/
                    Reserved for later phases
```

---

## Frontend (`frontend/src/`)

**One organizing principle:** app/ is thin routes; everything else is either shared
infrastructure (components/, lib/, services/, stores/, hooks/, types/, config/) or a
self-contained feature module (features/<name>/).

```
src/
│
├─ app/                         Next.js App Router — routes only, keep thin
│  ├─ layout.tsx                Root layout: fonts + Providers + AppShell
│  ├─ providers.tsx             'use client' — TanStack Query + KeyboardProvider
│  ├─ page.tsx                  Redirects to /library
│  ├─ library/
│  │  └─ page.tsx               Library root (Phase 2)
│  ├─ reader/
│  │  ├─ page.tsx               Reader landing
│  │  └─ [seriesId]/[chapterId]/page.tsx  (Phase 2)
│  ├─ create/
│  │  └─ page.tsx               (Phase 5)
│  ├─ search/
│  │  └─ page.tsx               (Phase 3)
│  ├─ ai/
│  │  └─ page.tsx               (Phase 3)
│  └─ settings/
│     └─ page.tsx               (Phase 6)
│
├─ components/
│  ├─ ui/                       Shared primitives — never feature-specific
│  │  ├─ button.tsx             ✅
│  │  ├─ input.tsx              ✅
│  │  ├─ badge.tsx              ✅
│  │  ├─ card.tsx               ✅
│  │  ├─ dialog.tsx             ✅
│  │  ├─ progress.tsx           ✅
│  │  └─ virtual-list.tsx       (Phase 2 — for large library grids)
│  └─ layout/
│     ├─ app-shell.tsx          ✅ Sidebar + Topbar wrapper; owns shell shortcuts
│     ├─ sidebar.tsx            ✅ Nav links, collapse state
│     ├─ topbar.tsx             ✅ Hamburger toggle, breadcrumb slot
│     └─ page-placeholder.tsx   ✅ Scaffold for unbuilt routes
│
├─ features/                    Self-contained pillar modules
│  ├─ library/                  ✅
│  │  ├─ api.ts
│  │  ├─ hooks.ts
│  │  ├─ types.ts
│  │  ├─ index.ts
│  │  └─ components/
│  │     ├─ SeriesGrid.tsx
│  │     ├─ SeriesCard.tsx
│  │     ├─ ContinueReading.tsx
│  │     ├─ ImportDialog.tsx
│  │     ├─ LibraryToolbar.tsx
│  │     └─ LibraryView.tsx
│  ├─ reader/                   ✅
│  │  ├─ api.ts
│  │  ├─ hooks.ts
│  │  ├─ store.ts
│  │  ├─ index.ts
│  │  └─ components/
│  │     ├─ BasicReader.tsx
│  │     ├─ ReaderControls.tsx
│  │     └─ PageImage.tsx
│  ├─ ai/                       (Phase 3)
│  ├─ search/                   (Phase 3)
│  ├─ knowledge/                (Phase 4)
│  └─ create/                   (Phase 5)
│
├─ services/                    Cross-feature API infrastructure
│  ├─ http.ts                   ✅ Typed fetch wrapper — ApiError, request<T>
│  ├─ index.ts                  ✅ Re-exports
│  └─ system.ts                 ✅ Health check service
│
├─ stores/                      Zustand — global UI state only
│  └─ ui-store.ts               ✅ sidebarCollapsed, toggleSidebar
│
├─ hooks/                       Shared hooks (not feature-specific)
│
├─ lib/
│  ├─ cn.ts                     ✅ clsx + tailwind-merge
│  └─ keyboard/
│     ├─ types.ts               ✅ ShortcutDefinition, KeyCombo
│     ├─ match.ts               ✅ Combo parsing and matching
│     ├─ context.tsx            ✅ KeyboardProvider, useShortcut, useRegisteredShortcuts
│     └─ index.ts               ✅ Public surface
│
├─ config/
│  ├─ env.ts                    ✅ NEXT_PUBLIC_API_URL
│  └─ nav.ts                    ✅ primaryNav + secondaryNav definitions
│
└─ types/
   ├─ api.ts                    ✅ ApiError, ApiErrorBody, RequestOptions
   └─ library.ts                Series, Chapter, Page, ReadingProgress (partial — Phase 2 refines)
```

---

## Backend (`backend/`)

**Layer rule:** Routes → Services → Database. Business logic never lives in routes.

```
backend/
│
├─ main.py                      create_app() factory: CORS, error handlers, router
├─ requirements.txt
│
├─ api/
│  ├─ __init__.py
│  └─ router.py                 Aggregates all route modules into one APIRouter
│
├─ routes/                      HTTP shape only — parse input, call service, return output
│  ├─ __init__.py
│  ├─ system.py                 ✅ GET /  → SystemStatus
│  ├─ ai.py                     ✅ POST /ai/chat
│  ├─ library.py                ✅
│  └─ reader.py                 ✅
│
├─ services/                    Business logic and external integrations
│  ├─ __init__.py
│  ├─ ollama_service.py         ✅ OllamaService (injectable via Depends)
│  ├─ library_service.py        ✅
│  ├─ image_service.py          ✅
│  ├─ reader_service.py         ✅
│  ├─ ocr_service.py            (Phase 3)
│  ├─ embedding_service.py      (Phase 3)
│  └─ search_service.py         (Phase 3)
│
├─ database/                    Data layer — models, session, migrations
│  ├─ __init__.py               ✅
│  ├─ models.py                 ✅
│  ├─ session.py                ✅
│  └─ migrations/               Alembic (Phase 2)
│
├─ workers/                     Background tasks — never block the HTTP server
│  ├─ scanner.py                (Phase 2) recursive folder walk, upsert to DB
│  ├─ thumbnailer.py            (Phase 2) first-page → cover image
│  ├─ ocr_worker.py             (Phase 3)
│  └─ embedding_worker.py       (Phase 3)
│
├─ core/
│  ├─ __init__.py               ✅
│  ├─ config.py                 ✅ Settings (reads config/settings.json), get_settings()
│  └─ errors.py                 ✅ AppError, register_error_handlers, error envelope
│
└─ utils/                       ✅ path validation, folder scanner
   ├─ path_utils.py
   └─ scanner.py
```

---

## Running the app

**Backend** (from `backend/` directory):
```
venv/Scripts/uvicorn main:app --reload
```
→ `http://127.0.0.1:8000` — API docs at `/docs`

**Frontend** (from `frontend/` directory):
```
npm run dev
```
→ `http://localhost:3000`

**Environment variable (optional):** Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```
Defaults to `http://127.0.0.1:8000` if not set.

---

## Contracts

**Error envelope** — every non-2xx response from the backend:
```json
{ "code": "machine_readable", "message": "Human readable.", "details": {} }
```
Frontend's `ApiError` in `src/types/api.ts` parses this shape. Never break it.

**State ownership** — not negotiable:
- Server data (from the API) → TanStack Query
- Browser/UI state → Zustand
- Mix them and you get cache bugs and stale UI

**File policy** — the backend never copies user files. It indexes original paths in
the database and serves them via `FileResponse`. Only covers and generated images
are written to disk by the app.
