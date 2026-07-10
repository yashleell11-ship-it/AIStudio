# AIStudio — Chief Architect Report

**Date:** 2026-07-01  
**Reviewer:** Chief Software Architect  
**Scope:** Complete codebase — backend, frontend, connectors, download manager, reader, database, worker model, API, security, performance, scalability  
**Team context:** Cursor (reader stability, auto-update), Kimi (OCR infrastructure, Comick connector), Claude (architecture/planning)

---

## Table of Contents

1. [Architecture Report](#1-architecture-report)
2. [Scalability Review](#2-scalability-review)
3. [Security Review](#3-security-review)
4. [Technical Debt Report](#4-technical-debt-report)
5. [Refactoring Recommendations](#5-refactoring-recommendations)
6. [Merge Conflict Risk Map](#6-merge-conflict-risk-map)
7. [Production Readiness Checklist](#7-production-readiness-checklist)
8. [Next Milestone Roadmap](#8-next-milestone-roadmap)

---

## 1. Architecture Report

### 1.1 Overall Assessment

AIStudio has a structurally sound skeleton. The separation of concerns is coherent: feature-based frontend modules, clean route→service→database layering in the backend, and a well-designed connector abstraction for content sources. The foundation is better than most projects at this stage.

The critical problems are not structural design mistakes — they are implementation gaps: designed patterns that weren't carried all the way through (background tasks designed but not built, WAL designed but not set, Pydantic response models designed but routes returning raw dicts). These are correctness and reliability gaps, not architectural rewrites.

### 1.2 Frontend Architecture

**Strengths:**
- Feature-based module layout (`features/library`, `features/reader`, `features/downloads`, `features/sources`) is clean and scales correctly
- TanStack Query for server state, Zustand for UI state — correct separation, no bleed between the two
- Typed keyboard shortcut layer (`lib/keyboard/`) is a production-quality utility
- Scroll position restoration in `ChapterReader` using `requestAnimationFrame` double-frame technique is correct
- `VirtualPageList` for page rendering exists — virtualisation is present

**Gaps:**
- All route pages (`app/ai/page.tsx`, `app/search/page.tsx`, `app/create/page.tsx`, `app/settings/page.tsx`) are placeholder shells with no implementation
- `features/reader/types.ts` and `features/library/types.ts` include raw filesystem paths (`file_path`, `cover_path`, `folder_path`) — frontend types should never hold server filesystem paths
- No loading skeletons for the library grid — cards flash in, which degrades perceived performance on slow hardware
- No error boundary components — a single failed component can crash the whole page tree
- `debug.ts` in the reader exports a `readerDebug` function used with extensive `useEffect` hooks; this logging fires on every render cycle in development and should be behind a debug flag or removed in production builds

### 1.3 Backend Architecture

**Strengths:**
- `core/errors.py` is exemplary — uniform `AppError`, proper status codes, catch-all that doesn't leak internals
- `connectors/` is a genuinely good plugin architecture: `SourceConnector` ABC with a clear contract, `ConnectorDescriptor` metadata, `registry.py` with validation at module load time
- `DownloadManager` is the most mature piece of code in the backend — adaptive worker concurrency, speed tracking, SHA-256 verification, resume-from-partial, disk space guards, manifest-based recovery from interrupted downloads
- `connectors/http/` provides both async and sync clients with rate limiting, retries, and exponential backoff
- `TTLCache` is clean, generic, and thread-safe

**Gaps:**
- `library_service.py` is still synchronous and blocking — the most-used service blocks the event loop
- `_scan_status` process-global breaks multi-worker deployments (C2 from prior review)
- `models.py` lags DATABASE.md by 40+ columns — the code and the design have diverged
- No Alembic — schema changes break existing databases silently
- `PRAGMA journal_mode=WAL` not set — concurrent read+write blocks
- `chapter.number` is `Integer` not `REAL` — decimal chapters corrupt
- The `ai/chat` endpoint (`routes/ai.py`) is a stub — single synchronous Ollama call with no context, no streaming, no session management

### 1.4 Connector Architecture

**Strengths:**
- `SourceConnector` ABC is the best-designed part of the backend
- `AsyncConnectorHttpClient` / `SyncConnectorHttpClient` pair covers both usage patterns
- Rate limiting built into the HTTP client prevents connector implementations from accidentally hammering sources
- `TTLCache` gives connectors a cheap caching layer without Redis

**Gaps:**
- `find_page()` default implementation in `base.py:58-71` is catastrophic: it paginates through ALL series, loads ALL chapters for each, and searches ALL pages to find one page by ID. Any connector that doesn't override this method will make O(series × chapters × pages) API calls on every image proxy request. MangaDex and AsuraScans connectors must override `find_page()`.
- `BrowseService._fetch_url()` uses a new `httpx.get()` call (no connection pooling, no rate limiting, no retry) for cover images and page proxying — it bypasses the entire `SyncConnectorHttpClient` infrastructure built for this purpose
- `_INSTANCE_CACHE` in `registry.py` is a module-level dict. In a multi-worker deployment, each process has its own cache. This is acceptable for stateless connectors but will cause subtle bugs if any connector holds mutable state

### 1.5 Download Manager

The `DownloadManager` is the strongest subsystem. Specific quality markers:
- `_recover_interrupted()` on startup correctly handles the case where a process died mid-download
- `_tune_workers()` adaptive concurrency scales down on failure bursts
- `ChapterManifest` JSON file per chapter provides crash-safe resumption
- SHA-256 verification of every page after download
- `DiskSpaceError` with pre-queue disk check prevents partial downloads due to full disk
- `_assert_can_continue()` checks cancel/pause state between every page download

**Gaps:**
- `_process_download()` is 150 lines. The fetch loop, manifest management, and import step should be separate private methods for testability
- `_import_and_verify()` calls `LibraryService.index_downloads_root()` which is a full synchronous scan — a completed download triggers a library rescan of the entire downloads directory, blocking the worker thread for potentially minutes
- `datetime.utcnow()` is deprecated throughout — replace with `datetime.now(timezone.utc)`
- No WebSocket push when a download completes — the frontend must poll

### 1.6 Reader Architecture

**Strengths:**
- `ChapterReader` correctly uses IntersectionObserver for edge detection instead of scroll event math
- Scroll position saved with debounced `setTimeout` (250ms) to avoid write storms
- Keyboard shortcuts registered at the component level and cleaned up on unmount
- `scroll-storage.ts` provides localStorage persistence for scroll position

**Gaps (noted by Cursor agent — do not fix here):**
- Cursor Chat 1 owns reader stability; any gaps found here should be reported to that agent
- The `SourceReader` component reads from `app/reader/online/[sourceId]/[seriesId]/[chapterId]/page.tsx` — this is a separate component from the local `BasicReader`, creating two render paths that share no logic

### 1.7 API Design

- All routes return `dict[str, object]` with no `response_model` declaration — FastAPI cannot validate or document output shapes
- Route-level DI functions (`get_image_service`, `_browse_dep`) are inconsistently defined: some use `@lru_cache`, some use `Depends(factory)` directly, and the `get_image_service` pattern is duplicated across `routes/library.py` and `routes/reader.py`
- No versioning prefix (`/v1/`) — breaking changes will be painful
- `POST /library/import` returns 200 synchronously; designed contract requires 202 + task ID
- Sources route `GET /sources/{id}/pages/{page_id}/image` proxies image bytes through FastAPI — this is synchronous and blocks a uvicorn thread for the full HTTP round-trip to the source. At 10 concurrent readers this saturates the thread pool

---

## 2. Scalability Review

### 2.1 Current Scale Ceiling

| Component | Current ceiling | Reason |
|---|---|---|
| Concurrent users | ~3 | Synchronous scan + synchronous image proxy blocks all workers |
| Library size | ~10K chapters | N+1 ORM loads before denormalized counts added |
| Download throughput | Good | DownloadManager properly threaded |
| Search | N/A | Not implemented |
| Embeddings | N/A | Not implemented |

### 2.2 Bottleneck Map

**B1 — Synchronous library scan blocks the event loop (CRITICAL)**  
`LibraryService.import_folder()` is called from the HTTP request handler. With uvicorn's default single-process async model, this blocks ALL other requests for the scan duration. FastAPI's `run_in_threadpool` is available and should be used, or the endpoint should enqueue a background job.

**B2 — Image proxy is synchronous and unbounded (HIGH)**  
`GET /sources/{id}/pages/{page_id}/image` calls `BrowseService.resolve_page_image()` → `_fetch_url()` → `httpx.get()` synchronously. This is a blocking call holding a uvicorn worker thread for up to 30 seconds (the httpx timeout). At 10 concurrent readers of online content, all 10 threads are blocked waiting on remote image servers. This endpoint must be async.

**B3 — N+1 ORM loads in library listing (HIGH)**  
`list_series()` → `_series_summary()` loads `len(series.chapters)` and `sum(chapter.page_count for chapter in series.chapters)` — all chapters in memory per series, per grid render. Fix: add `total_chapters` and `total_pages` denormalized columns and maintain them via triggers or a service wrapper.

**B4 — `get_series()` cascades to all pages (HIGH)**  
Already documented in C3. Every series detail view loads chapters × pages into ORM objects.

**B5 — Connector `find_page()` default is O(series × chapters × pages) (CRITICAL)**  
Every online page proxy call that hits the default `find_page()` implementation makes an unbounded number of API calls. MangaDex has thousands of series. This will cause request timeouts, rate-limit bans, and memory exhaustion.

**B6 — No response caching layer (MEDIUM)**  
Source connector responses (series lists, chapter lists) are re-fetched on every request. The `TTLCache` exists in `connectors/http/cache.py` but is not used by the `BrowseService` facade — each `GET /sources/{id}/series` call hits the connector's API directly.

**B7 — SQLite without WAL serializes reads during writes (MEDIUM)**  
Download progress updates (every page downloaded) are writes. Library scans are writes. In the default journal mode, a reader opening a chapter during a download will wait for the current page's write to complete. WAL mode eliminates this.

**B8 — DownloadManager import step triggers full directory scan (MEDIUM)**  
After each chapter completes, `_import_and_verify()` calls `LibraryService.index_downloads_root()` which rescans the entire downloads directory. For a series-level queue of 179 chapters, this runs 179 full scans of a growing directory.

### 2.3 Scalability Roadmap

| Phase | Action | Expected impact |
|---|---|---|
| Immediate | WAL pragma | Eliminates read/write contention |
| Immediate | Fix `find_page()` in all connectors | Eliminates O(n³) page lookups |
| M3 | Async image proxy | 10× concurrent online reader capacity |
| M3 | Background task queue | Scan no longer blocks HTTP |
| M3 | Denormalized counts | Library grid renders without loading chapters |
| M4 | Response caching via TTLCache | Connector API calls reduced by ~90% |
| M5 | PostgreSQL migration | Removes SQLite write serialization at multi-user scale |

---

## 3. Security Review

### 3.1 Critical

**SEC-1 — Path traversal when no library roots registered**  
`image_service.py:96` — `validate_path_under_roots()` only executes `if roots:`. Empty roots list skips validation entirely. A crafted `cover_path` can read any file the server process has access to.  
**Fix:** Validation must be unconditional. Empty roots → deny all.

**SEC-2 — No authentication on any endpoint**  
Every route is fully public. This is acceptable for `127.0.0.1`-only binding but becomes critical immediately if the app is bound to `0.0.0.0` for NAS/Docker deployment (which is the intended use case in AGENTS.md). No documentation warns users against this.  
**Fix:** Before any non-localhost deployment documentation is published, ship a shared-secret middleware or API key requirement.

**SEC-3 — Connector `find_page()` default leaks all source data**  
The default `find_page()` in `SourceConnector.base.py:58-71` traverses every series, chapter, and page on the connected source just to find one page. If called with a maliciously crafted `page_id` that doesn't exist, it exhausts the source's full catalog — a server-side DoS against the upstream source.  
**Fix:** All browsable connectors must override `find_page()`. The default should raise `NotImplementedError`.

### 3.2 High

**SEC-4 — Raw filesystem paths in API responses**  
`cover_path`, `folder_path`, `file_path` returned in API payloads expose the server's full directory structure. `Page.file_path` is in the TypeScript types but the frontend uses `/reader/page/{id}/image` URLs — the path field serves no purpose and should be removed.

**SEC-5 — Zip-slip and zip-bomb not checked**  
`image_service.py` and `utils/scanner.py` open `.cbz`/`.zip` archives without checking member paths for `../` traversal or capping decompressed size. A malicious archive in a watched folder could write outside the extraction directory or exhaust memory.  
**Fix:** Validate archive member paths; cap total decompressed size.

**SEC-6 — Source image proxy relays arbitrary URLs to remote servers**  
`BrowseService._fetch_url()` fetches any URL returned by the connector without validation. A compromised connector (or a supply-chain attack on a connector package) can use the proxy to make the server fetch arbitrary internal network resources (SSRF).  
**Fix:** Validate proxied URLs against an allowlist of expected source domains; reject private IP ranges.

**SEC-7 — No rate limiting**  
AI endpoints (Ollama), download queuing, and library import are all unprotected. A runaway client or automated script can queue tens of thousands of downloads or hammer Ollama without any throttle.

**SEC-8 — `DEFAULT_USER_AGENT` in `http/client.py` references a GitHub URL**  
`AIStudio/0.1 (local manga reader; +https://github.com/aistudio)` — this URL doesn't exist and may eventually be registered by someone else. The User-Agent string will be sent with every connector HTTP request. Remove the URL reference.

### 3.3 Medium

**SEC-9 — CORS credentials flag with no origin assertion**  
`main.py:52` — `allow_credentials=True` is set globally. If `settings.cors_origins` is ever misconfigured to include `["*"]`, browsers will happily send credentials cross-origin. Add a startup assertion.

**SEC-10 — Connector instance cache holds shared mutable state**  
`_INSTANCE_CACHE` in `registry.py` is shared across all requests in a process. If a connector implementation holds mutable state (session tokens, rate limit counters), concurrent requests will race on that state without any locking.

**SEC-11 — Download manifest files are not validated on load**  
`ChapterManifest.load()` reads a JSON file from disk and deserializes it without schema validation. A corrupted or maliciously crafted `.aistudio-download.json` could cause unexpected behavior during resume.

### 3.4 Low

- `reload=True` hardcoded in `main.py:71` — must be driven by env var in production
- `datetime.utcnow()` deprecated in Python 3.12+; will raise in future Python versions
- Debug logging in `ChapterReader` via `readerDebug` fires unconditionally in production builds

---

## 4. Technical Debt Report

### 4.1 Debt by Category

**Schema debt (Severity: HIGH)**

The gap between `models.py` (implemented) and `DATABASE.md` (designed) represents the largest single piece of technical debt. Every week this gap widens, migrating existing user databases becomes more expensive.

Missing columns with Phase 2 feature dependencies:
| Column | Table | Blocked feature |
|---|---|---|
| `chapter.number` → REAL | chapters | Decimal chapters (13.5, 100.1) |
| `series.sort_title` | series | Correct sort order |
| `series.reading_status` | series | Library filters |
| `series.is_favorite` | series | Favorites |
| `series.total_chapters` | series | Grid without chapter loads |
| `series.total_pages` | series | Grid without page loads |
| `series.deleted_at` | series | Soft delete / rescan safety |
| `chapter.sort_key` | chapters | SQL-level chapter ordering |
| `chapter.is_read` | chapters | Per-chapter read tracking |
| `reading_progress.scroll_offset_px` | reading_progress | Scroll position persistence |
| `library.is_active` | libraries | Disable a library root |
| `library.last_scanned_at` | libraries | UI scan status |

No Alembic setup means every schema change requires users to delete their database.

**Duplication debt (Severity: MEDIUM)**

| Symbol | Duplicated in |
|---|---|
| `_chapter_sort_key()` | `library_service.py`, `reader_service.py` |
| `_extract_chapter_number()` | `utils/scanner.py`, `services/import_cleanup.py` |
| `get_image_service()` | `routes/library.py`, `routes/reader.py` |
| `get_image_service()` with `@lru_cache` | Produces two independent singletons |

**Sync/async debt (Severity: HIGH)**

The entire `connectors/` HTTP infrastructure was built async (`AsyncConnectorHttpClient`) but the connector implementations that use it call `asyncio.run()` internally to bridge to sync callers. This means async code wraps sync code wraps async code — three context switches per connector API call. The connectors should be fully async and the routes should use `async def`.

**Response model debt (Severity: MEDIUM)**

All six route files return `dict[str, object]`. No `response_model=` is declared on any endpoint. FastAPI's automatic documentation, response validation, and TypeScript codegen (if ever needed) all depend on declared response models. The TypeScript types in `features/*/types.ts` are manually maintained against these unvalidated dicts — drift is guaranteed.

**Test coverage debt (Severity: HIGH)**

- Tests exist only for library import and reader progress (`test_library_api.py`)
- No tests for downloads, connectors, sources browsing, AI chat, or image serving
- No frontend tests at all
- No integration tests that exercise the full stack (import → read → progress)
- `DownloadManager` — the most complex component — has no dedicated tests

**Startup debt (Severity: MEDIUM)**

`run_startup_migrations()` calls `ImportCleanupService(db).merge_all_orphans_global()` on every startup. This loads all series into memory and runs O(n²) comparisons to find orphan candidates. For a library with 10,000 series, this makes every startup slow and blocks the lifespan event for the full duration.

### 4.2 Debt Priority Order

1. Alembic + schema sync (blocks all future development safely)
2. WAL pragma (correctness, one line)
3. `chapter.number` → REAL (correctness, one migration)
4. Async image proxy (performance, security)
5. Response models on all routes (correctness, documentation)
6. Fix `find_page()` default (security, correctness)
7. Test coverage for downloads and connectors
8. Remove duplication (`_chapter_sort_key`, `_extract_chapter_number`, `get_image_service`)

---

## 5. Refactoring Recommendations

These are improvements that do not rewrite working logic. Each is scoped, safe to merge independently, and addressable by one agent without blocking others.

### R1 — Consolidate shared utilities (no-conflict, safe)

Create `utils/chapter_utils.py`:
```python
def extract_chapter_number(name: str) -> float | None: ...
def chapter_sort_key(chapter: Chapter) -> tuple: ...
```

Delete the four duplicated copies. Update imports in `library_service.py`, `reader_service.py`, `scanner.py`, `import_cleanup.py`.

**Risk:** Low. All four implementations are identical. Pure utility function.

### R2 — Single image service factory

Create `services/image_service.py::get_image_service()` as the canonical factory (it already exists there — remove the copies in route files).

### R3 — Add `response_model=` to all routes, one route file at a time

Start with `routes/system.py` (trivial), then `routes/downloads.py` (well-structured serialization already exists in `_serialize_download`). Convert `_serialize_download` to a Pydantic schema and use `response_model=`.

### R4 — Make all connector methods synchronous and use `SyncConnectorHttpClient`

The current async-in-sync bridging is a source of subtle bugs. Since the connectors are called from sync FastAPI route handlers via `BrowseService`, they should be synchronous all the way down. `AsyncConnectorHttpClient` can remain for future async route support.

### R5 — Move `BrowseService._fetch_url()` to use `SyncConnectorHttpClient`

Replace the raw `httpx.get()` call with the existing client infrastructure that has rate limiting, retries, connection pooling, and proper User-Agent headers.

### R6 — Split `_process_download()` into smaller methods

```python
def _fetch_pages(self, download, chapter_path, remote_pages, manifest, db): ...
def _finalize_download(self, download, chapter_path, remote_pages, db): ...
```

No behavior change. Makes the method testable and the error handling paths clearer.

### R7 — Move startup orphan cleanup to a background task

`merge_all_orphans_global()` in `run_startup_migrations()` should be a background task that runs after the server is accepting requests, not a blocking startup step. Use `asyncio.create_task()` in the lifespan context.

### R8 — Replace `window.setTimeout` in `ChapterReader` with `useEffect` cleanup

`window.setTimeout(() => { writeScrollPosition(scrollKey, scrollTop); }, SCROLL_SAVE_MS)` inside `updateScrollState` creates a new timer on every scroll event without clearing the previous one. This should be a `useRef` holding the timeout ID with proper cleanup.

---

## 6. Merge Conflict Risk Map

This section identifies files with the highest probability of concurrent modification by multiple agents. The goal is to prevent agents from producing incompatible changes that block merging.

### 6.1 High-Risk Files (multiple agents touching)

| File | Owners | Risk | Mitigation |
|---|---|---|---|
| `backend/database/models.py` | Kimi OCR (new tables), Cursor auto-update (possibly), Claude planning | HIGH — every agent adding tables | Each agent adds only their own models; never modify existing table definitions |
| `backend/database/session.py` | Any agent adding WAL pragma or Alembic init | MEDIUM | WAL pragma is a one-line addition; coordinate who adds it first |
| `backend/services/library_service.py` | Cursor (reader stability may touch import), Kimi (OCR may hook into scan) | HIGH — core shared service | Kimi OCR should add a separate `ocr_service.py`, not modify `library_service.py`. OCR hooks into post-scan events, not the scan itself |
| `backend/api/router.py` | Any agent adding new routes | LOW — append-only pattern | Each agent adds one `include_router()` line for their subsystem |
| `backend/main.py` | Any agent modifying startup | MEDIUM | DownloadManager startup is already there; OCR worker startup should be a separate function |
| `frontend/src/config/nav.ts` | Any agent adding a new page | LOW — append-only | Each agent adds their nav item; no modifications to existing entries |

### 6.2 Agent-Owned Files (no other agent should touch)

| Subsystem | Agent | Owned files — hands off |
|---|---|---|
| Reader stability | Cursor Chat 1 | `features/reader/components/*`, `features/reader/store.ts`, `features/reader/hooks.ts` |
| Auto-update system | Cursor Chat 2 | `services/system.py` (new), `routes/system.py` (extend only), any new `update_*` files |
| OCR infrastructure | Kimi Agent 1 | New `services/ocr_service.py`, new `workers/ocr_worker.py`, new `connectors/ocr/*` |
| Comick connector | Kimi Agent 2 | New `connectors/comick/*` — registry.py needs one line added |

### 6.3 Shared Infrastructure — Coordination Required

**`backend/database/models.py` merge protocol:**
- Each agent adds their own model classes at the END of the file
- Never modify existing class definitions
- Add new `Index()` and `UniqueConstraint()` inside new classes only
- No changes to `Base`, `Library`, `Series`, `Chapter`, `Page`, `ReadingProgress`, `Bookmark` without cross-team review

**`backend/api/router.py` merge protocol:**
- Each agent appends `api_router.include_router(their_router)` as the last line in their subsystem scope
- No reordering of existing include statements

**`backend/main.py` merge protocol:**
- Startup initialization for new subsystems (OCR worker, update checker) goes inside new helper functions called from `lifespan()`
- No modification to existing `run_startup_migrations()` or `create_app()` structure

### 6.4 Conflict Risk Score by File

```
models.py          ████████ HIGH
library_service.py ██████   HIGH  
main.py            ████     MEDIUM
session.py         ████     MEDIUM
api/router.py      ██       LOW
routes/*.py        ██       LOW (each agent owns their own file)
frontend/features/ ██       LOW (each agent owns their feature dir)
```

---

## 7. Production Readiness Checklist

### 7.1 Backend

| Item | Status | Priority |
|---|---|---|
| WAL journal mode enabled | ❌ MISSING | P0 |
| Alembic migrations set up | ❌ MISSING | P0 |
| `chapter.number` is REAL type | ❌ MISSING | P0 |
| Path traversal validation unconditional | ❌ VULNERABLE | P0 |
| Synchronous scan made non-blocking | ❌ MISSING | P0 |
| `find_page()` overridden in all connectors | ❌ MISSING | P0 |
| Raw filesystem paths removed from API | ❌ LEAKING | P1 |
| `datetime.utcnow()` replaced | ❌ DEPRECATED | P1 |
| Zip-slip protection on archive open | ❌ MISSING | P1 |
| Rate limiting on AI/expensive endpoints | ❌ MISSING | P1 |
| Response models on all routes | ❌ MISSING | P1 |
| `reload=True` driven by env var | ❌ HARDCODED | P1 |
| Authentication middleware (pre-NAS deployment) | ❌ MISSING | P1 |
| ZipFile context manager (no handle leak) | ❌ LEAKING | P2 |
| `_chapter_sort_key` / `_extract_chapter_number` deduplicated | ❌ DUPLICATE | P2 |
| `get_image_service()` factory deduplicated | ❌ DUPLICATE | P2 |
| `merge_all_orphans_global()` moved out of blocking startup | ❌ BLOCKING | P2 |
| CORS startup assertion (`*` + credentials) | ❌ MISSING | P2 |
| Download manifest schema validation | ❌ MISSING | P3 |
| Server-side URL validation for image proxy (SSRF) | ❌ MISSING | P3 |

### 7.2 Frontend

| Item | Status | Priority |
|---|---|---|
| Route pages are not placeholder shells | ❌ 4 pages are stubs | P0 |
| `file_path`/`cover_path` removed from API types | ❌ LEAKING | P1 |
| Error boundaries present | ❌ MISSING | P1 |
| Loading skeletons for library grid | ❌ MISSING | P2 |
| `readerDebug` disabled in production builds | ❌ ALWAYS ON | P2 |
| `window.setTimeout` race in scroll handler fixed | ❌ BUG | P2 |

### 7.3 Infrastructure

| Item | Status | Priority |
|---|---|---|
| Dockerfile for backend | ❌ MISSING | P1 |
| `db_path` configurable via env var | ❌ HARDCODED | P1 |
| `downloads_path` configurable via env var | ✅ In settings | OK |
| `venv/` outside or hidden inside `backend/` | ❌ Pollutes searches | P3 |
| Test coverage >50% on backend services | ❌ <10% | P1 |
| Tests for DownloadManager | ❌ MISSING | P1 |
| Tests for connectors (MangaDex, AsuraScans) | ❌ MISSING | P1 |

### 7.4 Before First Non-Localhost Deployment

These must ALL be resolved before telling any user to bind the server to `0.0.0.0`:

1. SEC-1 (path traversal fix)
2. SEC-2 (authentication middleware)
3. SEC-5 (zip-slip fix)
4. SEC-6 (SSRF fix on image proxy)
5. Raw filesystem paths removed from all responses
6. Rate limiting on expensive endpoints

---

## 8. Next Milestone Roadmap

This roadmap respects the parallel team structure. Each item is labeled with the responsible agent.

### Sprint 1 (Immediate — unblock all agents)

**All agents coordinate on:**
- [ ] WAL pragma in `session.py` — one-line fix, merge first to unblock all DB work
- [ ] `chapter.number` → REAL in `models.py` — requires Alembic, so:
- [ ] Alembic baseline migration from current `models.py` — must exist before any agent adds schema

**Claude (Architecture):**
- [ ] Write Alembic setup guide and migration template for the team
- [ ] Write per-agent implementation specs (OCR table DDL, update system schema, Comick connector protocol)
- [ ] Document the `models.py` merge protocol for the team

**Cursor Chat 1 (Reader stability):**
- [ ] Fix `window.setTimeout` race condition in `ChapterReader.updateScrollState`
- [ ] Fix scroll restoration double `requestAnimationFrame` edge case (pages load after frame)
- [ ] Add error boundary to reader page

**Cursor Chat 2 (Auto-update system):**
- [ ] Design update manifest format (`version.json` schema)
- [ ] `GET /system/version` endpoint returning current version
- [ ] `GET /system/update/check` endpoint polling for new version
- [ ] Frontend update notification banner

**Kimi Agent 1 (OCR infrastructure):**
- [ ] Add `chapter_ocr_status`, `ocr_pages` models to `models.py` (at end of file)
- [ ] `services/ocr_service.py` — Ollama vision call per page, result stored in `ocr_pages`
- [ ] `workers/ocr_worker.py` — pulls from task queue (schema below)

**Kimi Agent 2 (Comick connector):**
- [ ] `connectors/comick/connector.py` implementing `SourceConnector`
- [ ] **Must** override `find_page()` — do not rely on default
- [ ] Register in `registry.py` (one line append)
- [ ] `ConnectorDescriptor` metadata

### Sprint 2 (M3 Foundation)

**Shared infrastructure (coordinate before starting):**
- [ ] `background_tasks` table schema (see below)
- [ ] `workers/task_runner.py` — single-threaded poller
- [ ] `GET /tasks/{id}` endpoint

**Background task table (all agents read this schema):**
```sql
CREATE TABLE background_tasks (
    id          INTEGER PRIMARY KEY,
    task_type   TEXT NOT NULL,        -- 'scan', 'ocr_chapter', 'embed', 'thumbnail'
    payload     TEXT,                 -- JSON
    status      TEXT NOT NULL DEFAULT 'pending',
    priority    INTEGER NOT NULL DEFAULT 100,
    progress    REAL DEFAULT 0.0,
    error       TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at  DATETIME,
    finished_at DATETIME,
    scheduled_at DATETIME
);
CREATE INDEX ix_bg_tasks_status_priority ON background_tasks(status, priority, created_at);
```

**Claude (Architecture):**
- [ ] Write complete OCR pipeline spec for Kimi Agent 1
- [ ] Write Comick connector API contract for Kimi Agent 2
- [ ] Write auto-update system spec for Cursor Chat 2

**Cursor Chat 1 (Reader stability):**
- [ ] Online reader progress saving (currently no progress is saved for online chapters)
- [ ] Chapter preloading for next chapter

**Cursor Chat 2 (Auto-update system):**
- [ ] Background version check (poll on startup + every 4 hours)
- [ ] Download + apply update flow (platform-specific)
- [ ] Update history log

**Kimi Agent 1 (OCR infrastructure):**
- [ ] Hook OCR task enqueue to post-import event
- [ ] FTS5 virtual table for OCR text search
- [ ] `GET /series/{id}/ocr-status` endpoint

**Kimi Agent 2 (Comick connector):**
- [ ] Comick series metadata mapping
- [ ] Chapter listing with proper `number` (float) mapping
- [ ] Page image URL construction
- [ ] TTLCache integration for series/chapter lists

### Sprint 3 (M3 Completion)

- [ ] Cover thumbnail worker (replaces raw `cover_path` with `/covers/{id}` URL)
- [ ] Remove raw filesystem paths from all API responses
- [ ] Fix path traversal validation gap (SEC-1)
- [ ] `POST /library/import` → 202 + task ID
- [ ] Semantic embeddings pipeline (after OCR stabilizes)
- [ ] `GET /search` FTS5 + vector hybrid endpoint

### Milestone 4 Preview

After M3 is stable:
- AI chat with spoiler gating (builds on OCR + embeddings)
- Character extraction from OCR text
- Knowledge graph (characters, locations, timeline)
- Creation Studio: project + character data models (no image gen yet)
- AI provider abstraction (`AIProvider` protocol replacing direct Ollama calls)

---

## Appendix A: Critical One-Liners to Merge Immediately

These changes are safe, small, and unblock everyone. Any agent can merge these in the same PR as their other work.

**WAL mode (`backend/database/session.py`):**
```python
# In _configure_sqlite_pragmas or equivalent listener:
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=ON")
```

**Startup CORS assertion (`backend/main.py`):**
```python
if "*" in settings.cors_origins and settings.allow_credentials:
    raise RuntimeError("CORS: cannot use wildcard origin with allow_credentials=True")
```

**`find_page()` default changed to raise (`backend/connectors/base.py:58`):**
```python
def find_page(self, page_id: str) -> Page | None:
    raise NotImplementedError(
        f"{self.__class__.__name__} must override find_page() for safe page lookup."
    )
```

---

## Appendix B: Agent Communication Protocol

When one agent discovers a bug or needed change in another agent's subsystem:

1. **Do not fix it.** Write it down.
2. Drop a comment in the PR description: `[CROSS-AGENT: Cursor Chat 1] — Found X in file Y at line Z. Needs fix.`
3. That agent picks up the report in their next sprint.

When schema changes are needed by multiple agents in the same sprint:
1. Agree on the table DDL via the architecture team first.
2. Only one agent adds the table to `models.py`.
3. The other agent's migration depends on the first merge.
4. Merge order: schema-adding PR → feature-implementing PR.
