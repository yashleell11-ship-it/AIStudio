# AIStudio — Production Readiness Report
**Chief Software Architect**  
**Date:** 2026-07-01  
**Scope:** Reader · Sources · Downloads · OCR · Library Intelligence · Update System  
**Status:** Pre-production — blocked on critical bugs

---

## Executive Summary

The codebase is architecturally sound and has advanced well beyond the Phase 2 skeleton. All six subsystems are implemented and wired. However, **5 critical bugs** will cause data loss or hard failures in production, **11 performance issues** will become severe at scale, and **7 security gaps** exist that must close before any non-localhost deployment. The system is not ready to ship; it can be made ready in one focused sprint.

---

## 1. Production Readiness Report

### 1.1 Overall Rating: ⚠ PRE-PRODUCTION

| Subsystem | Functional | Safe | Scalable |
|---|---|---|---|
| Reader | ✅ | ⚠ | ✅ |
| Sources | ⚠ | ❌ | ❌ |
| Downloads | ✅ | ✅ | ✅ |
| OCR | ⚠ | ❌ | ❌ |
| Library Intelligence | ⚠ | ✅ | ❌ |
| Update System | ⚠ | ✅ | ⚠ |

---

### 1.2 Subsystem Analysis

#### Reader

The reader architecture is correct. `ChapterReader` uses `IntersectionObserver` for edge detection, `requestAnimationFrame` for scroll debouncing, and timer cleanup on unmount. Three issues remain:

**R-BUG-1 (Critical): Side effect executed during render.**  
`syncChapterScroll(scrollKey, scrollElement, initialScrollTop)` is called at line 293 of `ChapterReader.tsx` unconditionally at render time — not inside a `useEffect`. React may call render multiple times (Strict Mode, concurrent features). This mutates `scrollElement.scrollTop` during render, causing scroll position corruption and flickering.  
Fix: move the `syncChapterScroll` call into a `useLayoutEffect` keyed to `[scrollKey, initialScrollTop]`.

**R-BUG-2 (Minor): Timer ref type mismatch.**  
`scrollSaveTimerRef` is typed `useRef<number | null>` (line 59) but `window.setTimeout` already correctly returns `number` in browser context. No runtime bug, but the explicit type annotation is correct. No action needed — this is fine as written.

**R-BUG-3 (Minor): No error boundary.**  
The inline error render (lines 275–283) shows a static message with no retry button. A thrown exception in `VirtualPageList` propagates unhandled. A React `ErrorBoundary` wrapper around the reader route is missing.

#### Sources

The sources subsystem has functional gaps and a critical SSRF hole:

**S-BUG-1 (Critical): SSRF — no URL allowlist on `_fetch_url`.**  
`BrowseService._fetch_url` (line 256, `browse_service.py`) accepts any URL from a connector's `page.remote_url` or `series.cover_url` and fetches it with `httpx.get()`. A malicious connector (or URL injected via connector metadata) can reach internal addresses: `http://127.0.0.1:11434` (Ollama), `http://169.254.169.254` (cloud metadata). No allowlist, no host validation.

**S-BUG-2 (Major): Dead code — unused cached singleton.**  
In `routes/sources.py`, `_browse_dep` (line 16) is defined with `@lru_cache` but `BrowseDep` uses `Depends(get_browse_service)` — an uncached factory. `_browse_dep` is never used and `BrowseService` is reinstantiated on every request. Either consolidate to one pattern or delete `_browse_dep`.

**S-BUG-3 (Major): Redundant network call in `get_chapters`.**  
`browse_service.get_chapters` (line 155–165) calls `connector.get_series(series_id)` only to check if the series exists before calling `connector.get_chapters(series_id)`. This is an extra network round-trip per chapter-list request. The existence check adds no safety — `get_chapters` should stand alone and raise `AppError` if the connector returns an empty list.

**S-BUG-4 (Major): `find_page` raises NotImplementedError — online reader broken.**  
The `find_page` fix applied today is correct for safety but has an immediate consequence: `BrowseService.resolve_page_image` calls `connector.find_page(page_id)` (line 226). Every browsable connector that has not overridden `find_page` will return HTTP 500 for every image proxy request. The online reader is non-functional until every browsable connector provides an implementation.

#### Downloads

Downloads is the most mature subsystem. No critical bugs found. The frontend uses correct TanStack Query mutation patterns. One scalability issue:

**D-PERF-1: No real-time progress push.**  
`useDownloads` polls at a fixed stale time. During an active download, progress updates only when the query refetches. Users see stale progress bars. Consider SSE or WebSocket for the download queue, or a short `refetchInterval` (e.g., 2 seconds) while any download is active.

#### OCR

The OCR pipeline is architecturally sound but has two critical bugs:

**OCR-BUG-1 (Critical): Page-failure retry restarts the entire job from scratch — O(n²).**  
In `ocr_pipeline._process_job` (lines 186–193), when a single page fails OCR, the entire job is reset to `"queued"` with `retry_count += 1`. On restart, the job reprocesses all prior pages (skipped cheaply via `existing` check), hits the failing page again, and retries indefinitely. For a 200-page chapter with a corrupt page at position 199, this means 199 "skip" queries per retry, up to `ocr_max_retries` times. The failed page should be recorded in a per-page failure log and skipped on subsequent attempts; the job should only fail when the failure rate exceeds a threshold.

**OCR-BUG-2 (Critical): `PageText` rows orphaned when pages are re-scanned.**  
`library_service._persist_scan` line 299: `self._db.query(Page).filter(Page.chapter_id == chapter.id).delete()` bulk-deletes all pages for updated chapters. `PageText` has a FK to `pages.id` with no cascade delete. Rescan of any already-OCR'd chapter creates orphaned `PageText` rows pointing to deleted page IDs. SQLite with `foreign_keys=ON` will raise an `IntegrityError` on delete unless cascade is added. Even if SQLite allows orphans, search will return ghost results.

**OCR-PERF-1: DB query inside `_pool_lock`.**  
`_dispatch` (line 91–113) holds `_pool_lock` while querying the DB for pending jobs. Lock contention proportional to DB latency. Fetch job IDs outside the lock, then re-acquire only to update `_active_ids`.

**OCR-PERF-2: OCR engine re-created per job, not per thread.**  
`get_ocr_engine` is called inside `_process_job` (line 131) which creates a new engine on every job. EasyOCR loads neural network weights — this is minutes of startup time per job. Engine instances must be per-thread (thread-local storage) and reused.

**OCR-SEARCH: Full-table ILIKE scan.**  
`OcrSearchService.search` does `ILIKE` across `ChapterText.full_text` with no index. At 100,000 chapters this scans gigabytes of text. FTS5 is already set up for `series_fts` — a `chapter_texts_fts` virtual table should be created alongside `chapter_texts`. This was flagged in session.py's `_init_fts5` pattern.

#### Library Intelligence

Architecturally clean but contains three O(N²) algorithms that are acceptable at 100 series and catastrophic at 10,000:

**LI-PERF-1 (Critical at scale): `get_similar_series` — O(N×Q) where Q = tag query per candidate.**  
Lines 174–200: loads ALL non-deleted series into a Python list, then fires a `COUNT` query to the DB per candidate series to count shared tags. With 5,000 series in the library, this is 5,000 DB round-trips per API call. Fix: use a single SQL `GROUP BY` query with a join on `series_tags`.

**LI-PERF-2 (Critical at scale): `get_recommendations` — same O(N²) pattern.**  
Lines 247–254 fires a `COUNT(SeriesTag)` query per candidate. Fix: same SQL aggregation approach.

**LI-PERF-3: N+1 in `list_tags`.**  
Line 481: fires one `COUNT(SeriesTag)` query per tag in the loop. 200 tags = 200 DB queries. Fix: single `GROUP BY tag_id` query.

**LI-BUG-1: `_series_summary` loads chapters in memory via lazy relationship.**  
Line 648: `chapter_count = len(series.chapters)` and `page_count = sum(...)` trigger a lazy load of all chapters for every series in a result set. In `search_series`, `Series` objects are fetched individually by rowid without `joinedload(Series.chapters)`. Every search result fires N additional chapter queries.

**LI-BUG-2: Three divergent serializations of `ReadingProgress`.**  
- `LibraryService._progress_dict` (line 592) omits `scroll_offset_px` and `started_at`.  
- `LibraryIntelligenceService._progress_dict` (line 763) includes both.  
- `ReaderService.save_progress` response (line 81) omits `scroll_offset_px`.  
These diverge silently. Frontend code consuming different endpoints gets inconsistent shapes.

#### Update System

Solid architecture. One blocking issue for production:

**UPD-BUG-1 (Major): `manual_check` blocks the HTTP thread.**  
In `routes/updates.py` line 141–150, when `trigger_check` returns `False` (a check is already running), the route falls through to `service.run_check(trigger="manual")` which runs synchronously in the request handler. With 50 tracked series requiring network calls, this blocks the HTTP worker thread for potentially minutes, causing timeouts for all other requests.  
Fix: return HTTP 409 `{"code": "check_already_running"}` when the manager is busy, instead of running synchronously as fallback.

**UPD-SCALE-1: `known_chapter_ids` as JSON text blob.**  
`SeriesTracker.known_chapter_ids` (line 503, `models.py`) stores a sorted JSON array of all known chapter IDs. A series with 2,000 chapters produces a ~40 KB text blob re-serialized on every update check. At 500 tracked series, each check round deserializes and re-serializes 20 MB of JSON. Fix: normalize into a `known_chapter_ids` join table.

---

### 1.3 Schema Bugs

**SCH-BUG-1 (Data corruption): `chapter.number` is `Integer`, not `Float`.**  
`Chapter.number` is `Mapped[int | None]` (line 102, `models.py`). Chapter 13.5 becomes 13. Common in manhwa with bonus chapters (e.g., "Chapter 125.5 — Omake"). This truncation silently corrupts chapter ordering and breaks adjacent-chapter navigation. Fix: change to `Float` with a migration.

**SCH-BUG-2: No cascade delete on `Chapter` → `OcrJob` / `PageText`.**  
`Chapter.ocr_jobs` relationship has no `cascade="all, delete-orphan"`. `_persist_scan` issues raw SQL `DELETE` against pages, bypassing ORM cascades. Orphaned `PageText` rows are guaranteed on any rescan of an OCR'd chapter (see OCR-BUG-2).

**SCH-BUG-3: `Bookmark.page_id` never set.**  
`reader_service.add_bookmark` (line 125) creates a `Bookmark` with `series_id`, `chapter_id`, `page` (integer number), and `note` — but never sets `page_id` (FK to `pages.id`). The FK column exists on the model (line 186) but is always NULL. The `page_ref` relationship is always `None`.

---

## 2. Integration Checklist

### Cross-Subsystem Wiring

- [ ] **OCR → Library**: `register_post_import_hook` mechanism exists in COORDINATION.md spec but is NOT yet in `library_service.py`. Auto-queue on import is not wired.
- [ ] **OCR → Intelligence**: `register_post_ocr_hook` mechanism is not yet in `ocr_pipeline.py`. The intelligence service has no trigger from OCR completion.
- [ ] **Downloads → Library index**: `DownloadManager` calls `index_downloads_root` after completion (verify in `download_manager.py` — not read in this session, confirm present).
- [ ] **Downloads → Update tracker sync**: `sync_downloaded_trackers` exists in `update_service.py` but must be called after a chapter download completes. No hook confirmed.
- [ ] **Update → Downloads auto-queue**: `_on_new_chapters` callback in `update_service.py` is `None` at startup. Auto-download is never triggered even when `auto_download_enabled=True`.
- [ ] **OCR search using FTS5**: `OcrSearchService` uses ILIKE, not FTS5. The `chapter_texts_fts` virtual table needs to be created in `_init_fts5`.

### API Router Registration

- [ ] `ocr_router` confirmed in `router.py`
- [ ] `updates_router` confirmed in `router.py`
- [ ] No intelligence router observed in `routes/` — `library_intelligence_service.py` exists but no corresponding `routes/intelligence.py` was found. Library intelligence endpoints may be missing entirely.

### Frontend Integration

- [ ] `features/updates/` exists with `UpdatesView`, `NotificationBell`, and `UpdateSettingsPanel`. Confirm wired into navigation.
- [ ] No `features/ocr/` frontend module found. OCR queue management has no UI.
- [ ] No intelligence search UI found. `GET /intelligence/search` (if it exists) has no frontend.
- [ ] `UpdateBanner` — not found in `app-shell.tsx`. The banner from SPEC_CURSOR_CHAT2 is unimplemented.

---

## 3. Testing Checklist

### P0 — Tests required before any merge

- [ ] `test_ocr_pipeline.py`: page-level retry does not restart from page 1; job completes when failure rate < 50%
- [ ] `test_library_service.py`: rescan of OCR'd chapter does not orphan PageText rows (requires cascade delete fix)
- [ ] `test_reader.py`: `syncChapterScroll` is not called during render (verify effect placement)
- [ ] `test_update_service.py`: `manual_check` with busy manager returns 409, does not block
- [ ] `test_image_service.py`: zip-slip attempt raises `AppError` not `KeyError`
- [ ] `test_browse_service.py`: `_fetch_url` with `http://127.0.0.1` raises `AppError("ssrf_blocked")`

### P1 — Tests required before production

- [ ] `test_library_intelligence.py`: `get_similar_series` with 1,000 series completes in < 500ms (SQL aggregation, not Python loop)
- [ ] `test_library_intelligence.py`: `get_recommendations` with 1,000 series completes in < 500ms
- [ ] `test_library_intelligence.py`: `list_tags` fires exactly 1 DB query (not N+1)
- [ ] `test_ocr_search.py`: full-text search uses FTS5 MATCH, not ILIKE
- [ ] `test_update_service.py`: tracker with 2,000 known chapters serializes/deserializes correctly
- [ ] `test_session.py`: WAL pragma is set on new connections
- [ ] `test_chapter_number.py`: chapter 13.5 stored and retrieved as 13.5, not 13
- [ ] `test_browse_service.py`: `find_page()` not called in online reader flow (confirm reader chapter endpoint builds page list without `find_page`)

### P2 — Regression tests

- [ ] Adjacent chapter navigation wraps correctly at series boundaries
- [ ] Reading progress includes `scroll_offset_px` in all three service responses (consistency)
- [ ] Collections CRUD with duplicate name returns 422, not 500
- [ ] Scan status resets correctly when a second scan is attempted while first is running
- [ ] OCR job cancel while processing: job status becomes "cancelled" and worker exits cleanly

---

## 4. High-Priority Bug List

Ordered by severity. Each entry names the file, approximate line, and the fix.

### P0 — Data corruption or hard crash

| # | File | Line | Bug | Fix |
|---|---|---|---|---|
| B1 | `database/models.py` | 102 | `chapter.number` is `Integer` — truncates 13.5 to 13 | Change to `Float`; add Alembic migration |
| B2 | `services/library_service.py` | 299 | `DELETE` pages bypasses ORM cascade — orphans `PageText` rows | Add `cascade="all, delete-orphan"` to `Chapter.pages` and `Chapter.ocr_jobs` relationships; or add FK `ON DELETE CASCADE` in migration |
| B3 | `services/ocr_pipeline.py` | 186–193 | Page failure restarts entire job — O(n²) page re-processing | Track per-page failure; skip permanently failed pages; fail job only when failure rate > threshold |
| B4 | `frontend/…/ChapterReader.tsx` | 293 | `syncChapterScroll` called during render — scroll corruption on Strict Mode | Move to `useLayoutEffect(() => { syncChapterScroll(...) }, [scrollKey, initialScrollTop])` |
| B5 | `routes/updates.py` | 149 | `service.run_check()` called synchronously in HTTP handler when manager busy | Return 409 `check_already_running` instead |

### P1 — Silent failures or security gaps

| # | File | Line | Bug | Fix |
|---|---|---|---|---|
| B6 | `services/browse_service.py` | 256 | SSRF — no host allowlist on `_fetch_url` | Validate URL scheme is `https` and host is not RFC-1918/loopback before fetch |
| B7 | `services/reader_service.py` | 125 | `Bookmark.page_id` never set | Set `page_id` from `Page.id` lookup in `add_bookmark` |
| B8 | `services/image_service.py` | 41 | ZipFile opened twice per archive page (list + read) — wasted I/O | Open once, call `namelist()` then `read()` within same context manager |
| B9 | `services/image_service.py` | 91–99 | Cover path for ZipFile skips root validation — path traversal | Validate cover zip path under library roots before opening |
| B10 | `routes/sources.py` | 16–21 | `_browse_dep` with `@lru_cache` defined but `BrowseDep` uses uncached factory — dead code | Remove `_browse_dep`; `BrowseService` is stateless so `Depends(get_browse_service)` is correct |
| B11 | `services/library_intelligence_service.py` | 481 | N+1: one COUNT query per tag in `list_tags` | Replace with single `GROUP BY tag_id` subquery |

### P2 — Missing integrations

| # | Area | Gap | Fix |
|---|---|---|---|
| B12 | OCR → Library | Post-import hook not wired | Add `_post_import_hooks` mechanism to `library_service.py`; call from `import_folder` success path |
| B13 | Updates → Downloads | `_on_new_chapters` is always `None` | Register auto-download callback in `main.py` lifespan if `auto_download_enabled` |
| B14 | Intelligence | No route file found | Create `routes/intelligence.py` and register in `router.py` |
| B15 | OCR Search | ILIKE scan, FTS5 not used | Add `chapter_texts_fts` to `_init_fts5`; update `OcrSearchService.search` to use FTS5 MATCH |

---

## 5. Recommended Work for the Next Development Milestone

Organized into three sequential sprints.

---

### Sprint A — Stability (all agents, 1 week)

Goal: no data loss, no silent failures, tests pass.

**Priority order:**

1. **`chapter.number` → `Float`** (SCH-BUG-1)  
   - Change `models.py` Integer → Float  
   - Write Alembic migration `0001_chapter_number_float`  
   - Update `library_service._compute_sort_key` to handle float  
   - Update `update_service._chapter_sort_key` (already handles `None`, but verify float case)

2. **Add ORM cascade deletes** (SCH-BUG-2)  
   ```python
   # models.py — Chapter
   pages: Mapped[list[Page]] = relationship(
       back_populates="chapter", order_by="Page.number",
       cascade="all, delete-orphan"
   )
   ocr_jobs: Mapped[list[OcrJob]] = relationship(
       back_populates="chapter", order_by="OcrJob.created_at",
       cascade="all, delete-orphan"
   )
   ```
   Also add `PageText` → `Page` cascade:
   ```python
   page_text: Mapped[PageText | None] = relationship(
       back_populates="page", uselist=False, cascade="all, delete-orphan"
   )
   ```

3. **OCR retry logic** (OCR-BUG-1)  
   Track per-page failures in a local dict during job processing. Skip pages that have already failed in this run. Only re-queue the job if the failure is transient (Ollama unavailable); never re-queue for corrupt image data.

4. **`syncChapterScroll` move to `useLayoutEffect`** (R-BUG-1)  
   Cursor Chat 1 owns this. Flagged here for awareness.

5. **`manual_check` 409 on busy** (UPD-BUG-1)  
   One-line fix in `routes/updates.py`.

6. **SSRF protection on `_fetch_url`** (S-BUG-1)  
   Add URL validation function. Reject private/loopback hosts. Enforce `https` scheme.

---

### Sprint B — Performance (backend agents, 1 week)

Goal: all O(N²) algorithms eliminated, FTS5 search live.

1. **`get_similar_series` — SQL rewrite**  
   Replace Python loop with:
   ```sql
   SELECT s.id, COUNT(st.tag_id) * 3 + ... AS score
   FROM series s
   LEFT JOIN series_tags st ON st.series_id = s.id AND st.tag_id IN (...)
   WHERE s.id != :source_id AND s.deleted_at IS NULL
   GROUP BY s.id
   ORDER BY score DESC
   LIMIT :limit
   ```

2. **`get_recommendations` — SQL rewrite**  
   Same pattern. One query instead of N per candidate.

3. **`list_tags` — single aggregation query**  
   Replace `COUNT` loop with `func.count(SeriesTag.series_id)` grouped by `tag_id`.

4. **FTS5 for OCR search**  
   Add `chapter_texts_fts` to `_init_fts5`. Rewrite `OcrSearchService.search` to use FTS5 `MATCH` with `snippet()`.

5. **OCR engine per-thread**  
   Use `threading.local()` to cache one engine instance per worker thread.

6. **`_dispatch` — release lock before DB query**  
   Query pending jobs outside `_pool_lock`, re-acquire only to update `_active_ids`.

---

### Sprint C — Integration (all agents, 1 week)

Goal: all six subsystems are fully wired end-to-end.

1. **Create `routes/intelligence.py`**  
   Expose `LibraryIntelligenceService` endpoints: search, similar, recommendations, reading history, statistics, favorites, collections, tags.

2. **Wire OCR post-import hook**  
   Add `_post_import_hooks` to `library_service.py`; register OCR auto-queue handler in `main.py` lifespan when `ocr_auto_queue=True`.

3. **Wire Update → Downloads auto-download**  
   Register `_on_new_chapters` callback in `main.py` lifespan when `auto_download_enabled=True`.

4. **Normalize `ReadingProgress` serialization**  
   Create a single `_serialize_progress(progress)` function in a shared util or base service. All three services import and call it.

5. **OCR queue UI**  
   Create `features/ocr/` frontend module: job list, queue button on series detail, progress display.

6. **`UpdateBanner` integration**  
   As per SPEC_CURSOR_CHAT2 — banner in `app-shell.tsx` outside scroll container.

7. **`known_chapter_ids` normalization** (UPD-SCALE-1)  
   Create `known_chapter_ids` join table; migrate from JSON text blob. Alembic migration `0003_known_chapter_ids_table`.

---

## Appendix: Files Requiring Immediate Attention

| File | Action |
|---|---|
| `database/models.py:102` | `chapter.number` Float; cascade deletes |
| `services/library_service.py:299` | Cascade or FK `ON DELETE CASCADE` required before rescan |
| `services/ocr_pipeline.py:186` | Per-page failure tracking; no job restart |
| `services/browse_service.py:256` | SSRF allowlist |
| `services/library_intelligence_service.py:174,247` | SQL aggregation replacement |
| `services/library_intelligence_service.py:481` | N+1 tag count |
| `routes/updates.py:149` | 409 on busy, not synchronous run |
| `frontend/…/ChapterReader.tsx:293` | Move to `useLayoutEffect` |
| `routes/sources.py:16` | Remove unused `_browse_dep` |
| `services/reader_service.py:125` | Set `Bookmark.page_id` |
| `database/session.py` | Add `chapter_texts_fts` to `_init_fts5` |
