# AIStudio — Second-Pass Architecture Review
**Chief Software Architect**
**Date:** 2026-07-01 (post "overnight changes")
**Scope:** Full re-review of Reader · Sources · Downloads · OCR · Library Intelligence · Update System
**Compares against:** `docs/PRODUCTION_READINESS_REPORT.md`

---

## Note on Scope of Changes

There is no git history in this repository (`git log` shows zero commits), so I diffed the current file contents directly against what I read in the previous session. **Only `services/library_intelligence_service.py` and `services/ocr_pipeline.py` were substantively changed.** Every other flagged file — `models.py`, `library_service.py`, `browse_service.py`, `ChapterReader.tsx`, `routes/updates.py`, `routes/sources.py`, `reader_service.py`, `app-shell.tsx` — is byte-for-byte identical to yesterday's review. Report this to the team: **five of the six subsystems received no fixes overnight.**

---

## 1. Integration Report

### 1.1 Correction to Prior Report

My earlier claim that "no intelligence router was found" was **wrong** — `routes/library.py` already exposes the full `LibraryIntelligenceService` surface (`/library/series/{id}/similar`, `/library/recommendations`, `/library/search`, `/library/statistics`, `/library/collections`, `/library/tags`, `/library/reading-calendar`, `/library/series/{id}/metadata-quality`). The intelligence layer is fully wired into the API. I should have grepped `routes/` contents more carefully before writing B14. Correcting the record now.

### 1.2 Genuine Fixes Landed Overnight

| Item | Status | Evidence |
|---|---|---|
| B11 — N+1 in `list_tags` | ✅ **Fixed** | `list_tags` (line 801) now does one `GROUP BY tag_id` query and a dict lookup, not a query per tag |
| LI-PERF-1 — `get_similar_series` O(N²) | ✅ **Fixed** | Line 283–353 now scores via a single SQL subquery joined against `Series`, no per-candidate query |
| `search_series` | ✅ **Improved** | Rewritten with FTS5-first lookup, relevance scoring (exact/prefix/substring/author/engagement), diversity cap — well beyond the original ask |
| OCR job-level infinite retry loop | ✅ **Fixed** | Old bug (job resets to `queued` forever on any page failure) is gone. Per-page retry with exponential backoff (`_process_page`, line 296–387) now isolates retries to the failing page |
| OCR adaptive concurrency | ✅ **New** | `_tune_workers` (line 263) scales worker count down under high failure rate — good defensive addition, not something I asked for but a sound production hardening |

### 1.3 New Bug Introduced by the Partial Fix

**NEW-BUG-1 (Major): `get_recommendations` still N+1 despite doing the SQL join.**  
Lines 387–413 build `tag_subq` — a `GROUP BY` subquery that already computes `shared_tags` per candidate series and joins it onto the candidate query. This is the correct pattern (same one used successfully in `get_similar_series`). But then the scoring loop at lines 419–432 **ignores the joined `tag_subq.c.shared_tags` value** and re-fires a fresh `func.count(SeriesTag.tag_id)` query per candidate:
```python
for s in candidates:
    ...
    if tag_subq is not None:
        shared_tags = (
            self._db.query(func.count(SeriesTag.tag_id))
            .filter(SeriesTag.series_id == s.id, SeriesTag.tag_id.in_(liked_tag_ids))
            .scalar() or 0
        )
```
This is the exact N+1 pattern LI-PERF-2 called out yesterday — the join was built and then unused. At 5,000 candidates this is still 5,000 DB round-trips per `/library/recommendations` call. Fix: select `tag_subq.c.shared_tags` in the outer query (it's already a joined column) instead of re-querying.

### 1.4 Genuinely Improved But Not Fully Closed

**OCR-BUG-1 (downgraded Critical → Major): single bad page still fails the whole job.**  
The infinite-requeue loop is gone (good — the O(n²) storm from yesterday's report cannot happen anymore). But `_process_page` still `raise`s when per-page retries are exhausted (line 356), and that exception propagates to `_process_job`'s `except Exception` handler, which marks the **entire job** `"failed"` (line 449–454). A single permanently corrupt page (e.g., truncated image, unsupported color profile) means the chapter never completes OCR, even though 199/200 pages succeeded and were already committed to `PageText`. A manual retry reprocesses cheaply (skips already-done pages via the `existing` check) but hits the same corrupt page and fails again — the job can never complete without manual intervention on that one page.  
Recommended: catch `OcrRecognitionError` per-page in `_process_job`, record a `pages_failed` counter, and only raise/fail the job if `pages_failed / pages_total` exceeds a threshold (matches what I originally recommended). Otherwise mark the job `"completed_with_errors"` and let search/reading work over the partial text.

### 1.5 Confirmed Still Broken (no change from yesterday)

All of these are unchanged since the last review — see full detail and fixes in `PRODUCTION_READINESS_REPORT.md`. Re-verified directly in the files:

- **B1** — `chapter.number` still `Integer` (`models.py:114,148`) — 13.5 truncates to 13
- **B2** — No cascade delete on `Chapter.pages` / `Chapter.ocr_jobs` (`models.py:130,133`) — rescans still orphan `PageText`
- **B4** — `syncChapterScroll(...)` still called directly in the render body of `ChapterReader.tsx:293`, not in an effect
- **B5** — `routes/updates.py:149` still falls through to a synchronous `service.run_check()` on the request thread when the manager is busy
- **B6** — `browse_service._fetch_url` (line 267) still has no host/scheme allowlist — SSRF still open
- **B7** — `reader_service.add_bookmark` (line 125) still never sets `Bookmark.page_id`
- **B10** — `routes/sources.py:16` still defines the unused `_browse_dep` alongside the real `BrowseDep`
- **UPD-SCALE-1** — `SeriesTracker.known_chapter_ids` still a JSON text blob, not a join table
- **UPD-BUG "auto-download callback"** — `_on_new_chapters` in `update_service.py` is still never registered from `main.py`; `auto_download_enabled` has no effect
- **No OCR frontend** — still no `features/ocr/` module; OCR queueing has no UI
- **No `UpdateBanner`** — `app-shell.tsx` is unchanged; no update banner rendered anywhere

### 1.6 Merge Risk Assessment

Since only two files changed, current merge risk is **low** for this snapshot — but it reveals a process gap: **whoever is editing `library_intelligence_service.py` and `ocr_pipeline.py` is not the same agent(s) who own the other four subsystems**, and no PR/commit record exists to attribute the changes or review them before they landed. This violates the coordination protocol in `docs/specs/COORDINATION.md` (no PR header, no verification gate confirmation). Recommend: require every agent to commit their own changes so `git log` becomes the source of truth for what changed and who changed it — right now review requires diffing file contents by hand, which does not scale past two files.

---

## 2. High-Priority Bug List

Ordered by severity, deduplicated against items already open from the previous report.

| # | Severity | File | Line | Bug | Status |
|---|---|---|---|---|---|
| 1 | **Critical** | `database/models.py` | 114 | `chapter.number` truncates decimal chapters | Still open |
| 2 | **Critical** | `database/models.py` | 130, 133 | No cascade delete — rescans orphan `PageText`/`OcrJob` rows | Still open |
| 3 | **Critical** | `services/browse_service.py` | 267 | SSRF — no allowlist on `_fetch_url` | Still open |
| 4 | **Major** | `services/library_intelligence_service.py` | 419–432 | `get_recommendations` N+1 despite already-joined `shared_tags` column | **New** |
| 5 | **Major** | `services/ocr_pipeline.py` | 356, 449 | Single bad page fails entire OCR job with no partial-completion path | Downgraded from Critical, still open |
| 6 | **Major** | `frontend/…/ChapterReader.tsx` | 293 | Scroll sync executed during render, not in an effect | Still open |
| 7 | **Major** | `routes/updates.py` | 149 | Synchronous fallback blocks HTTP thread when manager busy | Still open |
| 8 | **Minor** | `services/reader_service.py` | 125 | `Bookmark.page_id` never populated | Still open |
| 9 | **Minor** | `routes/sources.py` | 16 | Dead code: unused `_browse_dep` | Still open |
| 10 | **Minor** | `services/update_service.py` | — | `_on_new_chapters` callback never registered; auto-download setting is a no-op | Still open |

---

## 3. Production Readiness Score

### Overall: **42 / 100** — Pre-production, blocked

| Category | Score | Rationale |
|---|---|---|
| Correctness | 55/100 | Two Critical data-corruption paths remain open (chapter number truncation, cascade orphaning) |
| Security | 30/100 | SSRF is unpatched and reachable from any browsable connector; this alone blocks any non-localhost deployment |
| Performance | 60/100 | Real, verified improvement in `get_similar_series` and `list_tags`; `get_recommendations` still O(N) round-trips; OCR search still ILIKE, not FTS5 |
| Integration completeness | 45/100 | Intelligence API is more complete than previously credited; but OCR has no frontend, update banner is unbuilt, auto-download callback unwired |
| Process / auditability | 20/100 | No commits, no PR trail, no way to attribute or review changes except manual file diffing — this is the single biggest operational risk right now |

The score moved from last session mainly because two real algorithmic fixes landed cleanly, offset by the discovery that the other four subsystems are untouched and that there is no change-tracking process in place at all.

---

## 4. Recommended Next Milestone

The plan from the previous report (Sprint A: Stability → Sprint B: Performance → Sprint C: Integration) is still the correct shape, but resequence to close the gap this review exposed:

### Sprint 0 (immediate, before any more feature work): Establish auditability
1. **Initialize git properly.** Make an initial commit of the current tree, require every subsequent agent change to land as its own commit with a descriptive message. Without this, architecture review is reduced to manual byte-diffing, which will not scale past two files.
2. **Adopt the PR header template from `COORDINATION.md`** for every change, even single-agent solo work — it is currently unused.

### Sprint A — Stability (carried over, still not started)
1. `chapter.number` → `Float` + Alembic migration
2. Add `cascade="all, delete-orphan"` to `Chapter.pages`, `Chapter.ocr_jobs`, `Page.page_text`
3. SSRF allowlist on `browse_service._fetch_url` — reject private/loopback hosts, enforce `https`
4. Move `syncChapterScroll` call into `useLayoutEffect` in `ChapterReader.tsx`
5. `routes/updates.py` — return 409 instead of synchronous fallback

### Sprint A.5 — Close out this review's new findings (small, fast)
6. Fix `get_recommendations` to select `tag_subq.c.shared_tags` from the join instead of re-querying per candidate — this is a one-line change now that the subquery already exists
7. In `ocr_pipeline._process_job`, catch per-page `OcrRecognitionError` and only fail the job when `pages_failed / pages_total` exceeds a threshold (e.g. 50%); otherwise mark `"completed_with_errors"`

### Sprint B — Performance (unchanged from prior report, partially pre-empted)
- OCR full-text search → FTS5 (`chapter_texts_fts`), replacing the current ILIKE scan
- OCR engine instance reuse per worker thread

### Sprint C — Integration (unchanged, still all open)
- Wire `_on_new_chapters` callback in `main.py` lifespan for auto-download
- OCR queue frontend module (`features/ocr/`)
- `UpdateBanner` in `app-shell.tsx`
- `known_chapter_ids` → join table
- Remove dead `_browse_dep`; set `Bookmark.page_id`
