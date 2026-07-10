# ManhwaManiacs — Complete Architecture Review

**Date:** 2026-07-11 · **Reviewer:** Claude (acting architect) · **Codebase:** `~/dev/aistudio` (Forgejo `yash/aistudio`)
**Scope:** Full application review — backend (FastAPI/Python), frontend (Next.js 16), mobile (Flutter), database, connectors, download/reader/OCR engines, tests, docs. **Read-only phase produced this report; a bounded set of safe cleanups follows it (see §14).**
**Out of scope (frozen, per instruction):** Cloudflare, tunnel, Caddy, Docker/CI infrastructure, deploy engine. Those are complete and are not redesigned here.

> **Naming note.** The repo directory is `aistudio` (an internal codename for an abandoned "AI creation studio" direction). The shipping product is **ManhwaManiacs**, a manga/manhwa reader + multi-source aggregator, deployed publicly at manhwamaniacs.xyz. This report uses "ManhwaManiacs" for the product and `aistudio` only for the path.

---

## 1. Executive summary

ManhwaManiacs is a **well-engineered single-process, single-user, local-first manga reader and aggregator** with three clients (Next.js web, Flutter Android, and a headless API) over a FastAPI + SQLite backend. The core engineering is genuinely good: typed SQLAlchemy 2.0 models with sensible indexing, a robust resumable download engine with a strong test suite, clean connector abstractions with real SSRF defenses, a shared (non-duplicated) reader component tree on the web, and the best-covered tier — Flutter — at nearly 1:1.8 test-to-source.

The debt is **not sloppy code — it is architectural mismatch between three things that disagree with each other**:

1. **The code** says: single-user, no-auth, local-first, single-process, SQLite, one machine.
2. **The deployment** says: public on the internet at manhwamaniacs.xyz, reachable by anyone.
3. **The docs** say: a 50-table, multi-user, Postgres-ready, AI-comic-*creation* studio — ~1/3 of which describes software that does not exist.

The single most urgent finding is the collision of (1) and (2): **a public app with zero authentication that exposes unauthenticated arbitrary-path filesystem import, full-database export, and database replacement.** That is a live security exposure, not a theoretical one. Everything else — the in-process singleton workers that forbid multi-worker scaling, the absence of a repository seam, no Alembic, no shared API contract, the four competing product names — is real but secondary.

**Overall grade: B for the code, D for its fitness to how it is currently deployed.** The gap between those two is the roadmap.

**Top 5, in priority order:**
1. **Put the entire API behind authentication** (§9 Critical) — it is public and unauthenticated today.
2. **Fix the unauthenticated path-import / backup-restore vulnerabilities** (§9 Critical) — these bypass the otherwise-solid path-containment guard.
3. **Add application CI** (§9 Critical) — there is *no* lint/typecheck/test gate anywhere in the repo.
4. **Introduce a repository/service seam and make the background workers process-safe** (§9 High) — the two changes that unblock every future scaling story.
5. **Reconcile the docs with reality** (§9 High) — a third of the documentation actively misleads any new contributor (human or agent).

---

## 2. Current architecture

### 2.1 System context

```
                          ┌───────────────────────────────────────────┐
                          │         Cloudflare edge  (FROZEN)          │
                          │   tunnel → Caddy → :8000  (Host routing)   │
                          └───────────────────────┬───────────────────┘
                                                  │  (public, no auth)
      ┌───────────────────┬─────────────────────┴────────────────────┐
      │                   │                                            │
┌─────┴──────┐     ┌──────┴───────┐                            ┌──────┴────────┐
│  Next.js   │     │   Flutter    │                            │  Raw API /    │
│  web (SSR) │     │   Android    │                            │  scripts      │
│ React 19   │     │  Riverpod    │                            │               │
└─────┬──────┘     └──────┬───────┘                            └──────┬────────┘
      │  TanStack Query   │  dio                                      │
      └───────────────────┴──────────────────┬────────────────────── ┘
                                              │  HTTP JSON (envelope)
                              ┌───────────────┴────────────────┐
                              │      FastAPI app (1 process)     │
                              │  api/router.py → 11 routers      │
                              ├──────────────────────────────────┤
                              │  In-process singleton managers    │
                              │  (started in lifespan):           │
                              │   • DownloadManager  (threads)    │
                              │   • OcrManager       (threads)    │
                              │   • UpdateScheduler  (loop)       │
                              ├──────────────────────────────────┤
                              │  Services layer (business logic)  │
                              │  Connectors (5 sources + registry)│
                              ├──────────────────────────────────┤
                              │  SQLAlchemy 2.0  →  SQLite (WAL)   │
                              │  FTS5 search · files on local disk │
                              └───────────────────────────────────┘
                                              │
                       ┌──────────────────────┴───────────────────────┐
                       │  External manga sources (scraped):            │
                       │  AsuraScans · MangaDex · MangaKatana ·        │
                       │  Toonily (curl_cffi/chrome131) · DemonicScans │
                       └───────────────────────────────────────────────┘
```

### 2.2 Request lifecycle (read path — the hot path)

```
Client GET /reader/chapter/{id}
  → routes/reader.py          (envelope, pagination validation)
    → reader_service           (business logic, ReadingProgress)
      → SQLAlchemy session      (per-request, WAL, foreign_keys ON)
        → SQLite
  → page images: GET /reader/page/{id}
    → image_service            (validate_path_under_roots → serve file/zip entry)
```

### 2.3 Download path (the write/background hot path)

```
POST /downloads (enqueue)
  → DownloadQueue row
    → DownloadManager (singleton, thread pool)
      → connector.fetch_chapter_pages()  (rate-limited, SSRF-checked)
        → download_support.fetch_image_resumable()  (partial-file resume)
          → disk + Page rows
            → on completion: FULL LIBRARY re-index  ⚠ O(n²)  (download_manager.py:650)
```

---

## 3. Subsystem map

| Subsystem | Location | State | Notes |
|---|---|---|---|
| **API routing** | `backend/api/router.py` | Good | 11 routers; clean envelope + pagination. No auth/users router. |
| **Auth / users** | — | **Absent** | No login, JWT, session, or user model anywhere. |
| **Config** | `backend/core/config.py` | OK | `settings.json` + env override; `get_settings` lru_cache; not multi-process safe. Stale `D:/AIStudio` path comment; dead AI config keys. |
| **Database models** | `backend/database/models.py` | Good | ~24 typed tables, good indexing. INTEGER PKs (docs want BIGINT). |
| **DB session/migrations** | `backend/database/session.py` | Fragile | WAL + FK pragmas; **no Alembic** — hand-rolled ALTER dict + table-rebuild swap + FTS5 triggers. No `busy_timeout`. |
| **Search** | FTS5 via triggers | Good | Real full-text search; solid. |
| **Connectors** | `backend/connectors/*` | Good | 5 sources, registry pattern, SSRF guard, rate limiting. Adding a source edits 3 places (no autodiscovery). |
| **Download engine** | `backend/services/download_manager.py`, `download_support.py` | Good w/ 1 bug | Resumable, pause/resume/cancel/retry, well-tested. **O(n²) re-index bug** at `:650`; raw-httpx image fetch bypasses connector at `download_support.py:279`. |
| **Reader (backend)** | `backend/services/reader_service.py`, `image_service.py` | Good | Path containment enforced; minor: cover-zip read precedes roots check. |
| **OCR pipeline** | `backend/services/ocr_pipeline.py`, OcrManager | OK | pytesseract/easyocr; threaded singleton; no GPU/queue backpressure. |
| **AI chat** | `backend/routes/ai.py`, `ollama_service.py` | Vestigial | Single stateless `POST /ai/chat` → local Ollama; blocking, no lock/stream. Dead in public deploy. |
| **Updates / scheduler** | `backend/services/update_scheduler.py`, `update_service.py` | Good | Trackers, notifications, runs. Singleton loop — unsafe under multi-worker. |
| **Backup/restore** | `backend/routes/backup.py`, `core/backup_restore` | Works, unsafe | Round-trip tested. **Unauthenticated export + restore-on-restart.** |
| **Library / import** | `backend/services/library_service.py` | Fragile | Process-global `_scan_status`; sync/blocking scan. **Unauthenticated arbitrary-path import** (security). |
| **App distribution** | `backend/routes/app_distribution.py` | Deploy-coupled | Serves APK from fixed `mobile/build/...` path, unauthenticated. |
| **Frontend web** | `frontend/src/` (features/components/services/stores) | Good | Shared reader tree; TanStack Query + Zustand. `config/env.ts` **missing + gitignored → clean-clone build break**. |
| **Mobile** | `mobile/lib/` | Good, best-tested | Riverpod + go_router, Result/AppError. Always-HTTP image URLs; no local/offline storage; dead codegen deps. |
| **Logging** | `backend/core/errors.py` | Good | Generic 500 envelope; tracebacks server-side only. |
| **Analytics / notifications (push)** | — | Absent | Only in-app update notifications exist. |

---

## 4. Dependency graph (module-level, backend)

```
main.py ─ create_app ─┬─ api/router.py ─── routes/* ─── services/* ─┬─ connectors/* ─ http/{client,cf_client}
                      │                                             ├─ database/{models,session}
                      │                                             └─ core/{config,errors,outbound_security}
                      └─ lifespan ─ DownloadManager / OcrManager / UpdateScheduler  (singletons)
```

**Cross-tier duplication (the structural weak point):** the domain model is hand-written **three times** — Pydantic (`backend`), TypeScript (`frontend/src/services` + feature types), Dart (`mobile/lib/.../models`). There is **no shared OpenAPI contract**; a backend field rename compiles clean in all three and breaks the two live clients silently (confirmed: no cross-tier contract test exists).

**Notable intra-frontend cycle:** `features/reader/components/SourceReader.tsx` ↔ `features/sources/hooks.ts` (import cycle, §7).

---

## 5. Folder organization

- **Backend** — clean layered layout (`api/ · routes/ · services/ · connectors/ · database/ · core/`). The missing layer is a **repository seam**: services talk to SQLAlchemy sessions directly, so persistence and business logic are fused (blocks Postgres migration, unit-testing without a DB, and query-level optimization).
- **Frontend** — feature-first (`app/ features/ components/ services/ stores/ lib/ config/`), consistent and idiomatic for Next 16 App Router. One trap: `src/config/` is git-ignored by the root `.gitignore` `config/` rule, and `config/env.ts` is absent on disk — **a clean clone will not build** (verified via `git check-ignore`).
- **Mobile** — feature-first (`screen → provider → repository → dio`), the cleanest of the three tiers.
- **Docs** — 21 files / ~530 KB, mostly committed in one 2026-07-02 burst; bimodal (see §11).

---

## 6. Strengths

1. **Download engine** — resumable, cancelable, retry-aware, concurrency-bounded, and tested including `test_resume_after_restart`. Genuinely production-quality.
2. **SSRF defense** — `services/outbound_security.py`: HTTPS-only, per-connector host allowlist, DNS→public-address check, applied to image proxy and download fetch. This is done *right*.
3. **Connector design** — clean base class (`find_page` now correctly abstract), registry, rate limiting, per-source fixtures + a parametrized contract test across all 5 sources.
4. **Typed data layer** — SQLAlchemy 2.0 `Mapped`/`mapped_column`, thoughtful indexes, FTS5 search via triggers.
5. **Shared reader tree (web)** — `ChapterReader → VirtualPageList → PageImage`, no online/local duplication; TanStack Virtual for large chapters.
6. **Error hygiene** — generic 500 envelope, no stack-trace leakage, consistent API envelope + pagination (with tests asserting it).
7. **Mobile tier** — Result/AppError sealed-error pattern, ~1:1.8 test:source, widget + provider tests across features.
8. **Backend test suite** — 37 files / ~8.4k lines, fixture-based, in-memory SQLite, covers download/OCR/updates/backup-round-trip/migrations/SSRF.

---

## 7. Weaknesses & technical debt

**Architectural**
- **No repository seam** — services bound directly to SQLAlchemy; persistence not swappable or unit-testable in isolation.
- **In-process singleton workers** — DownloadManager/OcrManager/UpdateScheduler start once in lifespan and assume a single process. Multiple uvicorn/gunicorn workers would double-run schedulers and corrupt download/update state. Blocks horizontal scaling outright.
- **No shared API contract** — three hand-duplicated model layers; silent client breakage on backend change.
- **No Alembic** — migrations are `create_all` + a hand-rolled ALTER dict + a table-rebuild-swap + FTS5 trigger init, run on every boot. Fragile and unversioned.
- **Single-user / no-auth design baked in** — no user_id on any row; multi-user is a schema-wide change, not a feature add.

**Concrete bugs / dead code (cleanup candidates, §14)**
- `download_manager.py:650` — **O(n²)** full-library re-index on every chapter completion (performance bug).
- `download_support.py:279` — image fetch via raw httpx bypasses the connector (rate limit + impersonation lost).
- `frontend/src/config/env.ts` — **missing + gitignored → clean-clone build break** (highest-impact concrete bug).
- `frontend/src/features/library/hooks.ts:37-42` — `useContinueReading` cache key omits `limit` (stale-cache bug).
- `library_service.py:3` — unused `datetime` import; `:116` — process-global `_scan_status`.
- `connectors/http/client.py` — `AsyncConnectorHttpClient` entirely unused.
- `services/import_cleanup.py:102` — `_remove_orphan_series` dead.
- `frontend/.../LibraryToolbar.tsx:93` — dead ternary `seriesCount === 1 ? "series" : "series"`; no-op `onUnfollow` prop.
- `features/reader/components/SourceReader.tsx` ↔ `features/sources/hooks.ts` — import cycle.
- Mobile `reader_content.dart:329,700` — O(n) per-frame scan; `reader_screen.dart:120` — unawaited progress save.
- `backend/aistudio_backend.egg-info/*` — build artifacts tracked in git (already deleted in working tree).
- `main.py:129` — `uvicorn(reload=True)` in the `main()` entrypoint (dev-only).
- `requirements.txt` out of sync with `pyproject.toml` (omits `curl_cffi`, `ollama` version).
- Dead AI config (`config.py:32-38`) + dead `ollama` dependency; vestigial `/ai/chat`.

---

## 8. Risk assessment

### 8.1 Security — **Critical** (public app, zero auth)

| Risk | Location | Severity |
|---|---|---|
| No authentication anywhere on a public API | whole app | **Critical** |
| Unauthenticated arbitrary-path library import bypasses path-containment guard (register `/` as a root → read any image on disk + DoS full-disk scan) | `routes/library.py:316`, `library_service.py:127` | **Critical** |
| Unauthenticated backup export (full DB to anyone) | `routes/backup.py:42` | High |
| Unauthenticated backup import → DB replaced on next restart | `routes/backup.py:60` | High |
| No inbound rate limiting (only outbound connector throttle) | app-wide | High |
| Public app front-runs scrapers under server IP (ToS/legal) | connectors | Medium |
| Unauthenticated APK download from fixed path | `routes/app_distribution.py:33` | Low |

**Done well:** SSRF defense, path traversal guard (except the import bypass), no secret leakage, no error leakage, CORS wildcard guarded, no secrets in repo.

### 8.2 Scalability — **High**
Single-process singleton workers + single-node SQLite with a repo-derived absolute path. Cannot add web workers or nodes without redesign. Library grids hard-cap `per_page:200` with no pagination — unbounded as libraries grow.

### 8.3 Performance — **Medium**
The O(n²) re-index (`download_manager.py:650`) degrades sharply as the library grows. Blocking sync scans and blocking AI/OCR calls hold request/worker threads. Mobile per-frame O(n) scans in the reader.

### 8.4 Maintainability — **Medium-High**
Triple-duplicated models with no contract; no repository seam; hand-rolled migrations; and ~1/3 of docs actively misleading. Each of these multiplies the cost of every future change.

### 8.5 Dependency risk — **Low-Medium**
Backend pins exact and healthy (fastapi/pydantic/sqlalchemy/httpx all `==`). `curl_cffi` is a heavier, ToS-adjacent TLS-impersonation lib, but isolated to Toonily. `ollama` is dead weight. `requirements.txt`/`pyproject.toml` drift will ImportError a requirements-based install.

---

## 9. Priority roadmap

### 🔴 Critical (do before anything else — the deploy is public *now*)
1. **Authenticate the whole API** — shared secret / reverse-proxy auth / API key at minimum. The "single-user no-auth" assumption is invalid for a public deploy.
2. **Fix unauthenticated path-import + backup endpoints** — allowlist import base dirs (never `/`), gate `/library/import`, `/backup/import`, `/backup/export` behind auth.
3. **Add application CI** — one workflow running `pytest`, `tsc --noEmit` + `eslint` + `vitest`, `flutter test` on every push. None exists today.
4. **Add inbound rate limiting** (slowapi or proxy-level) on disk-scanning and connector-triggering endpoints.

### 🟠 High
5. **Introduce a repository/service seam** — decouple business logic from SQLAlchemy; unblocks testing, Postgres, and query optimization.
6. **Make background workers process-safe** — leader-elect or externalize the download/OCR/update schedulers, or enforce+document single-worker operation explicitly.
7. **Reconcile docs with reality** — move `CREATION_STUDIO.md`, `AI_PIPELINE.md`, and the AI/KG halves of `API.md`/`DATABASE.md` to `docs/future/` or delete; regenerate `API.md` from the real OpenAPI schema; finish the ManhwaManiacs rename across docs.
8. **Adopt Alembic** — replace boot-time hand-rolled migrations with versioned migrations.
9. **Fix the O(n²) download re-index** (`download_manager.py:650`) — incremental index on completion.
10. **Harden the deploy path** — remove `reload=True`, require `CORS_ORIGINS` at startup, serve APK from a stable location, enforce HTTPS for the mobile client, fix `D:/AIStudio` assumptions.

### 🟡 Medium
11. **Shared API contract** — generate TS/Dart types from OpenAPI; add a cross-tier contract test.
12. **Close connector-drift test gap** — scheduled CI job running the `integration`-marked live-source tests; add a DemonicScans fixture test.
13. **Frontend test coverage** — switch vitest to jsdom; add store + API-client + key component tests; wire up Playwright (config + `e2e/`).
14. **Route image downloads through the connector** (`download_support.py:279`) — restore rate limiting + impersonation.
15. **Pagination for library grids** — remove the `per_page:200` cap.

### 🟢 Low
16. Dead-code removal, naming cleanup, import-cycle fix, config drift — the §14 cleanups.
17. Mobile offline/local storage + local image URLs.
18. AI/OCR: GPU lock, queue backpressure, streaming (only if the AI direction is revived; otherwise remove).
19. BIGINT PKs if/when Postgres migration lands.

---

## 10. Testing gaps (summary)

- **Backend: strong** (37 files) — but live-source connector tests are `integration`-marked and skipped by default, so upstream HTML drift leaves the suite green while scraping breaks. DemonicScans has no dedicated test.
- **Frontend: weak** (9 files, node env only) — zero tests on `ui-store`, `services/http`, `app/*` routes, or `components/*`. Playwright is a dep with no config/`e2e/`.
- **Mobile: best** (64 files) — but no `integration_test/`.
- **Cross-tier: none** — a backend field rename passes all three suites and still breaks live clients.
- **Download resume**: tested only via mocked `fetch_image_resumable`, never real partial-file/corruption on disk.

---

## 11. Documentation assessment

~530 KB / 21 files, **bimodal**: an accurate "manga reader" layer plus a large aspirational "AI creation studio" layer with **zero backing code** (~174 KB, ~1/3 of all doc bytes, describes features that do not exist). The three files stamped "Canonical reference — all code must match" are the *least* accurate (`CREATION_STUDIO.md` ~100% fictional, `AI_PIPELINE.md` ~80%, `API.md` ~55%). `API.md` documents endpoints that don't exist and omits the real `/updates`, `/backup`, `/app`, `/sources` routers. Four competing product names in play (AIStudio / ManhwaManiacs / ManhwaStudio / `D:/AIStudio`).

**Trustworthy:** `README.md`, `SOURCES.md`, `ARCHITECTURE.md`, `specs/*`, the three architect/readiness reports. **Recommended contributor path:** README → SOURCES → architect reports → specs/. Treat VISION/PRODUCT/AI_PIPELINE/CREATION_STUDIO/API/DATABASE as a wish-list until reconciled.

---

## 12. Unknowns / open questions for the user

1. **Is the "AI creation studio" direction dead or deferred?** This decides whether ~174 KB of docs + the `ollama`/AI config get deleted or moved to `docs/future/`.
2. **Is public multi-user access intended,** or should the deploy be locked to you (single shared secret / Cloudflare Access)? This decides whether auth is "a gate in front" or "a full user model + per-row ownership."
3. **Postgres someday, or SQLite forever?** Decides whether the repository seam + Alembic + BIGINT PKs are worth doing now.
4. **Is the Flutter app expected to work offline?** It currently has no local storage and always-HTTP image URLs.

---

## 13. Recommended next milestone

**Milestone: "Public-safe baseline."** A single, coherent, shippable unit of work that closes the code↔deployment gap without touching product scope:

- Auth gate over the whole API (Critical 1).
- Fix path-import + backup auth (Critical 2).
- Application CI workflow (Critical 3).
- Inbound rate limiting (Critical 4).
- Deploy hardening: remove `reload=True`, require `CORS_ORIGINS`, HTTPS for mobile (High 10).
- Doc reconciliation + rename completion (High 7).

This is the smallest set that makes the current public deployment defensible. Everything in High/Medium (repository seam, Alembic, contract, worker safety) is the *next* milestone after this one and should be planned but not started until this ships.

---

## 14. Safe cleanups performed in this pass

Per the review brief, only **safe refactors, dead-code removal, obvious bugs, naming, docs, and organization** were auto-applied. No user-facing features, no redesigns, no speculative abstractions were added. All backend edits were verified with `py_compile` and a clean symbol-reference scan; the app test suites and `tsc`/`vitest` could not be run here because the toolchains (Python venv, `node_modules`) are not installed in this environment — that is expected (they run in Docker/CI), and the absence of an application CI pipeline is itself finding §9 Critical #3.

### Refactors completed / Files changed

| # | Change | File(s) | Kind |
|---|---|---|---|
| 1 | **Fixed clean-clone build blocker.** Anchored the `.gitignore` `config/` rule to `/config/` so it only ignores the repo-root backend runtime config and no longer swallows source dirs named `config/`. | `.gitignore` | Obvious bug |
| 2 | **Recreated the missing `env.ts`** (imported by `services/http.ts` and three feature `api.ts` files; previously absent on disk *and* git-ignored → `next build` failed from a clean checkout). Reconstructed from actual usage (`env.apiUrl`), mirroring the mobile `Env.defaultApiUrl` convention. | `frontend/src/config/env.ts` (new) | Obvious bug |
| 3 | **Fixed `useContinueReading` cache-key bug** — the TanStack Query key omitted `limit`, so different limits collided on one cache entry. Added `limit` to the key. | `frontend/src/features/library/hooks.ts` | Obvious bug |
| 4 | **Removed dead ternary** `seriesCount === 1 ? "series" : "series"` (identical branches) → plain `series`. | `frontend/src/features/library/components/LibraryToolbar.tsx` | Simplification |
| 5 | **Removed unused `datetime` import.** | `backend/services/library_service.py` | Dead code |
| 6 | **Removed dead private method** `_remove_orphan_series` (no callers; a thin passthrough to `merge_all_orphans_global`). | `backend/services/import_cleanup.py` | Dead code |
| 7 | **Removed the unused `AsyncConnectorHttpClient`** (never instantiated anywhere), its only referrer `SyncConnectorHttpClient.from_async_client`, and the now-unused `import asyncio`. All 5 connectors use only `SyncConnectorHttpClient`/`ConnectorHttpError`. | `backend/connectors/http/client.py` | Dead code |
| 8 | **This report.** | `docs/ARCHITECTURE_REVIEW_2026-07-11.md` (new) | Documentation |

### Deliberately NOT auto-changed (require decisions / are not "safe")

- **`AsyncConnectorHttpClient`'s replacement, the O(n²) download re-index, the repository seam, Alembic, auth, rate limiting, doc reconciliation, the `SourceReader`↔`sources/hooks` import cycle, `reload=True`, `requirements.txt`/`pyproject.toml` drift, the `D:/AIStudio` path comment, and the four-name rename** — these are either behavioral changes, redesigns, or security/feature work that the brief reserves for the approved roadmap (§9), not the auto-cleanup pass.
- The stale `aistudio_backend.egg-info/*` tracked files are already deleted in the working tree and are covered by the existing `*.egg-info/` ignore rule (`.gitignore:18`); no action needed beyond committing the deletion.

**Not committed.** All changes are left in the working tree for your review; nothing was staged or committed (per the no-auto-commit convention).

---

## 15. Ratified decisions & follow-up cleanup (2026-07-11)

After the report was delivered, two of the §12 open questions were answered by the owner. Both are now reflected in `docs/ROADMAP.md`.

### Decision 1 — Target access model: **real multi-user**
The product will grow into full user accounts with per-user ownership (auth + `user_id` on owned rows), not single-user/no-auth. This is a large, schema-wide change and is **sequenced, not implemented**: §9 Critical #1 (auth) becomes the first step, and a dedicated "Multi-user foundation" phase (accounts, per-row ownership, the repository seam, process-safe workers, Alembic) follows the "Public-safe baseline." No multi-user code was written in this pass.

### Decision 2 — AI is a **product capability, not an internal platform**
No local models, no Ollama/ComfyUI, no in-app AI creation studio. AI features will consume **external AI APIs** (recommendations, home feed, similar-series, reading/chapter/character/series summaries, search improvements, tag generation, metadata enrichment, smart collections, continue-reading). This was executed now as authorized dead-code/doc cleanup:

**Removed from the live codebase:**
| Change | File(s) |
|---|---|
| `/ai/chat` stub route | `backend/routes/ai.py` (deleted) |
| Ollama service wrapper | `backend/services/ollama_service.py` (deleted) |
| `/ai` router import + registration | `backend/api/router.py` |
| Dead AI config keys (`ollama_url`, `comfyui_url`, `default_chat`, `default_writer`, `default_reasoner`) | `backend/core/config.py` |
| `ollama==0.6.2` dependency | `backend/pyproject.toml`, `backend/requirements.txt` |
| Frontend `/create` + `/ai` placeholder pages | `frontend/src/app/create/`, `frontend/src/app/ai/` (deleted) |
| Sidebar nav entries + now-unused icon imports (`PenTool`, `Sparkles`) | `frontend/src/config/nav.ts` |
| Test key swapped off `ollama_url` → neutral `custom_setting` | `backend/tests/test_download_concurrency_settings.py` |

**Archived (preserved, not deleted):** `docs/CREATION_STUDIO.md` and `docs/AI_PIPELINE.md` → `docs/archive/ai-studio/` with a README explaining the decision.

**Roadmap rewritten:** `docs/ROADMAP.md` reset — old Phases 3–5 (AI Layer / Knowledge Graph / Creation Studio) removed; new phases are Public-safe baseline → Multi-user foundation → AI product features (external APIs) → Scale & polish.

**Verification:** `py_compile` passes on all touched backend files; a repo-wide grep confirms zero remaining references to `/ai/chat`, `ollama`, `OllamaService`, `ai_router`, or the removed config keys, and no callers of the deleted routes/pages.

**Left for a future naming pass (not auto-changed):** `default_project = "ManhwaStudio"` (`config.py:30`) and the stale `D:/AIStudio` path comment — these are part of the broader four-name reconciliation (§9 High #7), a naming decision rather than a mechanical cleanup.

### Still open (from §12)
Two questions remain and would refine the roadmap further: **(3)** SQLite forever vs. a future Postgres migration (decides how urgently the repository seam + BIGINT PKs matter), and **(4)** whether the Flutter app must work offline (it currently has no local storage). Neither blocks the Public-safe baseline milestone.
