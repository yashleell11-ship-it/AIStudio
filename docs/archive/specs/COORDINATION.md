# Multi-Agent Coordination Protocol
**Chief Architect:** AIStudio Architecture Team  
**Date:** 2026-07-01  
**Applies to:** All four parallel agents — read this before starting any work

---

## Merge Order Dependencies

Some work has ordering constraints. Everything else is fully parallel.

```
Phase 0 (parallel, no dependencies):
  ┌─ Cursor Chat 1 ──── Reader Stability (pure frontend, no shared files)
  ├─ Cursor Chat 2 ──── Auto-Update System (new files + 3 minimal shared touches)
  └─ Kimi Agent 1  ──── OCR Infrastructure (backend-only, new files + append-only models.py)

Phase 1 (after Kimi Agent 1 merges):
  └─ Kimi Agent 2  ──── Library Intelligence (depends on ocr_service._post_ocr_hooks existing)
```

Kimi Agent 2 can implement everything except the integration hook and end-to-end pipeline tests in parallel with Phase 0. Only the `register_post_ocr_hook` wiring requires Kimi Agent 1 to be merged first.

---

## Shared File Protocols

### `backend/database/models.py`

**Rule: append only. Never edit above your insertion point.**

```
[existing models — DO NOT TOUCH]
class Library ...
class Series ...
class Chapter ...
class Volume ...
class Page ...
class ReadingProgress ...
class Bookmark ...
class ImportHistory ...
class Download ...
class DownloadQueue ...
class SourceChapterLink ...

[Kimi Agent 1 appends here]
class BackgroundTask ...
class ChapterOcrStatus ...
class OcrPage ...
class SeriesAiStatus ...

[Kimi Agent 2 appends here — after Agent 1's classes]
class AiSummary ...
class Character ...
class CharacterAppearance ...
class AiSeriesMetadata ...
```

If agents work in parallel and both need to append, both can write their classes independently. The merge resolves to: keep all classes, preserve order (Agent 1's classes first, Agent 2's classes second).

### `backend/api/router.py`

**Rule: append `include_router()` lines only. No reordering.**

```python
# [existing lines — DO NOT TOUCH]
api_router.include_router(system_router)
api_router.include_router(library_router)
api_router.include_router(downloads_router)
api_router.include_router(reader_router)
api_router.include_router(sources_router)
api_router.include_router(ai_router)

# [Cursor Chat 2 appends]
api_router.include_router(update_router)

# [Kimi Agent 1 appends]
api_router.include_router(ocr_router)

# [Kimi Agent 2 appends]
api_router.include_router(intelligence_router)
```

All three lines are independent. Any order among the three new lines is acceptable.

### `backend/main.py` — `lifespan()` function

**Rule: add initialization inside `lifespan()` only. Each agent adds exactly what its spec says.**

Target state after all agents merge:
```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    if run_migrations:
        run_startup_migrations()
    else:
        init_db()

    # [Kimi Agent 1] — Task runner startup
    import services.ocr_service  # noqa: F401
    task_runner = get_task_runner()
    task_runner.start()

    # [Kimi Agent 2] — Intelligence handler registration  
    import services.intelligence_service  # noqa: F401

    # [Kimi Agent 2] — Hook registration (requires Kimi Agent 1's hook mechanism)
    from services.ocr_service import register_post_ocr_hook
    from services.intelligence_service import _on_chapter_ocr_completed
    register_post_ocr_hook(_on_chapter_ocr_completed)

    # [Kimi Agent 1 / shared] — Post-import OCR queuing
    if get_settings().ocr_auto_queue:
        from services.library_service import register_post_import_hook
        from services.ocr_service import _on_series_imported
        register_post_import_hook(_on_series_imported)

    yield

    # [Kimi Agent 1] — Shutdown
    task_runner.stop()
```

### `backend/core/config.py`

**Rule: each agent appends their settings block after all existing fields. Do not reorder.**

Cursor Chat 2 appends:
```python
update_manifest_url: str = "..."
update_channel: str = "stable"
update_check_enabled: bool = True
```

Kimi Agent 1: no config changes needed (OCR fields already exist: `ocr_engine`, `ocr_workers`, etc.)

### `frontend/src/components/layout/app-shell.tsx`

**Only Cursor Chat 2 modifies this file.** The change is one import and one component render. All other agents must not touch this file.

---

## Cross-Agent Required Coordination Points

These are the two places where agents have explicit dependencies:

### CP-1: `library_service.py` post-import hook

**Who adds it:** Kimi Agent 1  
**What to add:**
```python
# At module scope, after imports:
_post_import_hooks: list[Callable[[int], None]] = []

def register_post_import_hook(hook: Callable[[int], None]) -> None:
    _post_import_hooks.append(hook)
```

And in `import_folder()`, at the end of a successful import:
```python
for hook in _post_import_hooks:
    try:
        hook(series.id)
    except Exception:
        pass
```

**Who uses it:** Kimi Agent 1 (OCR auto-queue), Kimi Agent 2 indirectly (intelligence is triggered by OCR completion, not import)

### CP-2: `ocr_service.py` post-OCR hook

**Who adds it:** Kimi Agent 1  
**What to add:**
```python
# At module scope:
_post_ocr_hooks: list[Callable[[int, int], None]] = []

def register_post_ocr_hook(hook: Callable[[int, int], None]) -> None:
    _post_ocr_hooks.append(hook)
```

And at the end of `handle_ocr_chapter_task`, after marking the chapter completed:
```python
for hook in _post_ocr_hooks:
    try:
        hook(chapter_id, series_id)
    except Exception:
        pass
```

**Who uses it:** Kimi Agent 2 (registers `_on_chapter_ocr_completed`)

### CP-3: `_ollama_lock` shared across services

**Who owns it:** Kimi Agent 1 (defined in `ocr_service.py` as `_ollama_lock = threading.Lock()`)  
**Who imports it:** Kimi Agent 2 (`from services.ocr_service import _ollama_lock`)

This ensures all Ollama calls — OCR, summarization, character extraction — serialize through one lock and never cause GPU OOM.

---

## Bug Report Protocol

If any agent finds a bug outside their ownership:

1. **Do NOT fix it.**  
2. Add to a shared doc: `docs/specs/BUG_REPORTS.md`  
3. Format:
   ```
   [REPORTER: Kimi Agent 1] [AFFECTS: library_service.py:248]
   Description: _persist_scan deletes all pages on every rescan. Should use hash-based change detection.
   Severity: MEDIUM
   ```
4. The architect reviews bug reports and assigns them in the next sprint.

---

## Alembic Migration Coordination

Both Kimi agents create Alembic migrations. The migration history must be linear.

**Protocol:**
- Kimi Agent 1 creates migration file first (for OCR/task tables)
- Kimi Agent 2's migration must set `down_revision` to Kimi Agent 1's migration revision ID
- Both agents must coordinate the revision IDs before writing their migration files

**Placeholder revision IDs** (replace with actual Alembic-generated IDs):
- Kimi Agent 1 migration: `0001_add_ocr_task_tables`
- Kimi Agent 2 migration: `0002_add_intelligence_tables` with `down_revision = "0001_add_ocr_task_tables"`

**To generate a new migration revision:**
```powershell
cd backend
python -m alembic revision --autogenerate -m "add_ocr_task_tables"
```

---

## Verification Gates

Before merging any branch, the agent must confirm:

1. `npm run build` (frontend agents) or `pytest backend/tests/` (backend agents) passes
2. No changes outside owned files (run `git diff --name-only` and review)
3. No modification to existing model class definitions in `models.py`
4. All `# noqa: F401` comments on handler-registration imports are present
5. The shared file protocol rules above have been followed

---

## Communication Template

When filing a PR, include this header:

```
## Multi-Agent PR Header

Agent: [Cursor Chat 1 | Cursor Chat 2 | Kimi Agent 1 | Kimi Agent 2]
Sprint: [Phase 0 | Phase 1]

Files created:
- [list]

Files modified:
- [list] — [describe what changed, e.g., "appended 3 lines at EOF"]

Cross-agent dependencies satisfied:
- [ ] CP-1 present (if applicable)
- [ ] CP-2 present (if applicable)
- [ ] CP-3 imported (if applicable)

Shared file protocol compliance:
- [ ] models.py: only appended, no edits above insertion point
- [ ] router.py: only appended include_router lines
- [ ] main.py: only added lines inside lifespan()
- [ ] config.py: only appended new settings fields

Bug reports filed: [none | link to BUG_REPORTS.md entries]
```
