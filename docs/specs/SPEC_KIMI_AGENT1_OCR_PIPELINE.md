# Implementation Spec: OCR & AI Pipeline Infrastructure
**Agent:** Kimi Agent 1  
**Architect sign-off:** Chief Software Architect  
**Date:** 2026-07-01  
**Status:** Ready to implement

---

## 1. Goals

Build the complete background task queue and OCR pipeline infrastructure. This is the most critical M3 foundation piece — every other AI feature (summaries, embeddings, chat, character extraction) depends on it.

Deliverables:
1. `background_tasks` database table and task queue worker
2. OCR pipeline: per-page Ollama vision call → `ocr_pages` table → FTS5 search index
3. Status tracking: per-chapter and per-series OCR progress
4. REST endpoints for queue management and status polling

---

## 2. Scope

### In scope
- `background_tasks` table (the shared task queue for all future AI workers)
- `chapter_ocr_status` table
- `ocr_pages` table
- FTS5 virtual table for OCR text search
- `series_ai_status` table (denormalized progress tracking)
- `workers/task_runner.py` — the single-threaded task poller
- `services/ocr_service.py` — Ollama vision call, result persistence
- `routes/ocr.py` — queue, status, and search endpoints
- Hook OCR queuing to post-import event (see integration section)
- Alembic migration adding all new tables

### Out of scope
- Summarization (uses OCR output; Kimi Agent 2's domain)
- Embeddings and vector search (uses OCR output; future sprint)
- Character extraction (uses OCR + summaries; future sprint)
- Any frontend components
- Any modifications to `library_service.py` internals (see integration section for the correct hook pattern)

---

## 3. File Ownership

### Files this agent creates (new)
```
backend/workers/__init__.py
backend/workers/task_runner.py
backend/services/ocr_service.py
backend/routes/ocr.py
backend/migrations/versions/XXXX_add_ocr_and_task_tables.py   ← Alembic migration
```

### Files this agent modifies (minimal, append-only)
```
backend/database/models.py         ← append new model classes at the END only
backend/api/router.py              ← append include_router(ocr_router) as last line
backend/core/config.py             ← config fields already present (ocr_engine, etc.)
backend/main.py                    ← add task_runner.start() call in lifespan
```

### Files this agent MUST NOT modify
```
backend/services/library_service.py    ← owned by core; read the integration section
backend/services/download_manager.py  ← Cursor Chat 2 is nearby; leave alone
backend/services/reader_service.py
backend/routes/library.py
backend/routes/reader.py
backend/routes/sources.py
backend/routes/downloads.py
backend/routes/system.py
backend/connectors/*
frontend/**                            ← no frontend changes
```

---

## 4. Database Schema

### 4.1 Append to `models.py` — new models in this exact order

**IMPORTANT:** Append these classes after the last line of the existing `models.py` (`class SourceChapterLink`). Do not modify any existing class. Do not reorder existing classes.

---

#### `BackgroundTask`
```python
class BackgroundTask(Base):
    __tablename__ = "background_tasks"
    __table_args__ = (
        Index("ix_bg_tasks_poll", "status", "priority", "created_at"),
        Index("ix_bg_tasks_type", "task_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[str | None] = mapped_column(Text)       # JSON string
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # statuses: pending | running | completed | failed | cancelled
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    # lower number = higher priority; 0=critical, 10=user-initiated, 100=background
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(128))  # for future multi-worker
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)  # for deferred tasks
```

---

#### `ChapterOcrStatus`
```python
class ChapterOcrStatus(Base):
    __tablename__ = "chapter_ocr_status"
    __table_args__ = (
        UniqueConstraint("chapter_id", name="uq_chapter_ocr_status"),
        Index("ix_chapter_ocr_status_series", "series_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # statuses: pending | queued | running | completed | failed | skipped
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    ocr_pages_done: Mapped[int] = mapped_column(Integer, default=0)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("background_tasks.id"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
```

---

#### `OcrPage`
```python
class OcrPage(Base):
    __tablename__ = "ocr_pages"
    __table_args__ = (
        UniqueConstraint("page_id", name="uq_ocr_page"),
        Index("ix_ocr_pages_chapter", "chapter_id"),
        Index("ix_ocr_pages_series", "series_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), nullable=False)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"), nullable=False)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)           # raw OCR output
    text_cleaned: Mapped[str | None] = mapped_column(Text)   # normalized, deduplicated
    language: Mapped[str | None] = mapped_column(String(16)) # detected language code
    confidence: Mapped[float | None] = mapped_column(Float)  # 0.0–1.0
    model_used: Mapped[str | None] = mapped_column(String(128))
    is_ai_generated: Mapped[bool] = mapped_column(Integer, default=True)
    is_user_edited: Mapped[bool] = mapped_column(Integer, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
```

---

#### `SeriesAiStatus`
```python
class SeriesAiStatus(Base):
    __tablename__ = "series_ai_status"
    __table_args__ = (
        UniqueConstraint("series_id", name="uq_series_ai_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("series.id"), nullable=False)
    ocr_status: Mapped[str] = mapped_column(String(32), default="none")
    # none | partial | completed
    ocr_pct: Mapped[float] = mapped_column(Float, default=0.0)
    ocr_chapters_done: Mapped[int] = mapped_column(Integer, default=0)
    ocr_chapters_total: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
```

---

### 4.2 FTS5 Virtual Table

The FTS5 table is created in the Alembic migration, **not** in the SQLAlchemy ORM (SQLAlchemy does not support FTS5 virtual tables natively). Add this raw SQL to the `upgrade()` function of the migration:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_pages_fts USING fts5(
    text_cleaned,
    series_id UNINDEXED,
    chapter_id UNINDEXED,
    page_id UNINDEXED,
    content='ocr_pages',
    content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);

-- Triggers to keep FTS in sync with ocr_pages
CREATE TRIGGER ocr_pages_fts_insert AFTER INSERT ON ocr_pages BEGIN
    INSERT INTO ocr_pages_fts(rowid, text_cleaned, series_id, chapter_id, page_id)
    VALUES (new.id, new.text_cleaned, new.series_id, new.chapter_id, new.page_id);
END;

CREATE TRIGGER ocr_pages_fts_delete AFTER DELETE ON ocr_pages BEGIN
    INSERT INTO ocr_pages_fts(ocr_pages_fts, rowid, text_cleaned, series_id, chapter_id, page_id)
    VALUES ('delete', old.id, old.text_cleaned, old.series_id, old.chapter_id, old.page_id);
END;

CREATE TRIGGER ocr_pages_fts_update AFTER UPDATE ON ocr_pages BEGIN
    INSERT INTO ocr_pages_fts(ocr_pages_fts, rowid, text_cleaned, series_id, chapter_id, page_id)
    VALUES ('delete', old.id, old.text_cleaned, old.series_id, old.chapter_id, old.page_id);
    INSERT INTO ocr_pages_fts(rowid, text_cleaned, series_id, chapter_id, page_id)
    VALUES (new.id, new.text_cleaned, new.series_id, new.chapter_id, new.page_id);
END;
```

**In `downgrade()`** of the migration, drop triggers then the virtual table:
```sql
DROP TRIGGER IF EXISTS ocr_pages_fts_update;
DROP TRIGGER IF EXISTS ocr_pages_fts_delete;
DROP TRIGGER IF EXISTS ocr_pages_fts_insert;
DROP TABLE IF EXISTS ocr_pages_fts;
```

---

## 5. Background Task Queue — `workers/task_runner.py`

### Architecture

Single-threaded poller running in a daemon `threading.Thread`. The worker polls the `background_tasks` table for pending tasks, executes them one at a time (or up to `max_concurrent` for IO-bound tasks), and updates status.

**Why single-threaded for now:** SQLite allows only one writer at a time. A single-threaded worker never contends on the write lock during task execution. When PostgreSQL is adopted, this can be upgraded to a thread pool.

### Public Interface

```python
class TaskRunner:
    def __init__(self, *, poll_interval: float = 2.0) -> None: ...
    def start(self) -> None: ...       # start the background thread
    def stop(self) -> None: ...        # signal shutdown; blocks until thread exits
    def notify(self) -> None: ...      # wake up the poller immediately (call after enqueue)

def get_task_runner() -> TaskRunner: ...    # singleton
```

### Task type registry

```python
# In task_runner.py
TaskHandler = Callable[[dict], None]  # payload dict -> raises on failure

_HANDLERS: dict[str, TaskHandler] = {}

def register_handler(task_type: str, handler: TaskHandler) -> None:
    _HANDLERS[task_type] = handler
```

OCR service registers itself:
```python
# In services/ocr_service.py, called once at module import
from workers.task_runner import register_handler
register_handler("ocr_chapter", handle_ocr_chapter_task)
```

### Poll loop pseudocode

```
while not stop_event:
    task = claim_next_task(db)
    if task:
        handler = _HANDLERS.get(task.task_type)
        if handler:
            try:
                task.status = "running"
                task.started_at = now()
                db.commit()
                handler(json.loads(task.payload or "{}"))
                task.status = "completed"
                task.progress = 100.0
                task.finished_at = now()
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)
                task.finished_at = now()
            db.commit()
        else:
            task.status = "failed"
            task.error = f"No handler for task_type '{task.task_type}'"
            db.commit()
    else:
        stop_event.wait(timeout=poll_interval)  # sleep until notify() or timeout
```

### `claim_next_task` SQL

Claim the highest-priority pending task atomically:

```python
def claim_next_task(db: Session) -> BackgroundTask | None:
    task = (
        db.query(BackgroundTask)
        .filter(
            BackgroundTask.status == "pending",
            or_(
                BackgroundTask.scheduled_at == None,
                BackgroundTask.scheduled_at <= datetime.utcnow(),
            ),
        )
        .order_by(BackgroundTask.priority.asc(), BackgroundTask.created_at.asc())
        .with_for_update(skip_locked=True)   # PostgreSQL; SQLite: omit this
        .first()
    )
    return task
```

**SQLite note:** `with_for_update(skip_locked=True)` is not supported in SQLite. For SQLite, use a `try/except OperationalError` around the select and commit, or simply rely on the single-threaded worker never having concurrent claimers.

### Registration in `main.py`

In the `lifespan` async context manager, after `run_startup_migrations()`, add:

```python
from workers.task_runner import get_task_runner
import services.ocr_service  # noqa: F401 — registers the handler

task_runner = get_task_runner()
task_runner.start()
yield
task_runner.stop()
```

The `import services.ocr_service` side-effects the handler registration. The `# noqa: F401` suppresses the "unused import" lint warning.

---

## 6. OCR Service — `services/ocr_service.py`

### Public Interface

```python
def queue_chapter_ocr(
    chapter_id: int,
    series_id: int,
    *,
    priority: int = 100,
    db: Session,
) -> BackgroundTask:
    """Enqueue OCR for one chapter. Returns the task row. Idempotent."""

def get_chapter_ocr_status(chapter_id: int, db: Session) -> ChapterOcrStatus | None:
    """Return current OCR status for a chapter."""

def get_series_ocr_status(series_id: int, db: Session) -> SeriesAiStatus | None:
    """Return aggregate OCR status for a series."""

def search_ocr_text(
    query: str,
    *,
    series_id: int | None = None,
    limit: int = 20,
    db: Session,
) -> list[dict]:
    """FTS5 search across OCR text. Optionally scoped to a series."""

def handle_ocr_chapter_task(payload: dict) -> None:
    """Task handler — called by TaskRunner. payload = {"chapter_id": int, "series_id": int}"""
```

### `queue_chapter_ocr` — Idempotency

Before creating a new task, check for an existing `ChapterOcrStatus`:
- If status is `completed`: return without enqueuing
- If status is `queued` or `running`: return the existing task row
- If status is `pending`, `failed`, or does not exist: create/update the record and enqueue

```python
def queue_chapter_ocr(chapter_id, series_id, *, priority=100, db):
    existing = db.query(ChapterOcrStatus).filter_by(chapter_id=chapter_id).first()
    if existing and existing.status in ("completed", "queued", "running"):
        return existing.task  # already done or in progress

    task = BackgroundTask(
        task_type="ocr_chapter",
        payload=json.dumps({"chapter_id": chapter_id, "series_id": series_id}),
        priority=priority,
        status="pending",
    )
    db.add(task)
    db.flush()

    if existing is None:
        status_row = ChapterOcrStatus(
            chapter_id=chapter_id,
            series_id=series_id,
            status="queued",
            task_id=task.id,
        )
        db.add(status_row)
    else:
        existing.status = "queued"
        existing.task_id = task.id
        existing.error = None

    db.commit()
    get_task_runner().notify()
    return task
```

### `handle_ocr_chapter_task` — Core algorithm

```
Input: payload = {"chapter_id": int, "series_id": int}

1. Open a new SessionLocal() (task runs in its own thread)
2. Load Chapter, verify it exists and has pages
3. Update ChapterOcrStatus.status = "running", started_at = now()
4. Load all Pages for the chapter ordered by page.number
5. For each page:
   a. Check if OcrPage already exists for this page_id (resume support)
   b. If exists and text is not None: skip (already processed)
   c. Resolve the image file path from page.file_path or via archive extraction
   d. Read image bytes
   e. Call _ollama_vision_ocr(image_bytes, model) → raw_text
   f. Clean text: strip excess whitespace, deduplicate repeated lines
   g. Detect language (simple heuristic — CJK codepoints → "ko"/"ja"/"zh"; else "en")
   h. Upsert OcrPage row
   i. Increment ChapterOcrStatus.ocr_pages_done
   j. Update ChapterOcrStatus.progress
   k. db.commit() (commit each page for crash recovery)
6. Mark ChapterOcrStatus.status = "completed", finished_at = now()
7. Update SeriesAiStatus (see below)
8. db.close()
```

**If any page fails:**
- Log the error
- Set `OcrPage.text = None`, `OcrPage.confidence = 0.0`
- Continue to the next page (do not fail the entire chapter on one bad page)
- If more than 50% of pages fail, mark chapter status as `"failed"`

### Ollama vision call

```python
def _ollama_vision_ocr(image_bytes: bytes, model: str) -> str:
    """Call Ollama's vision API to extract text from an image."""
    import base64
    import httpx
    
    settings = get_settings()
    prompt = (
        "Extract all text from this manga/manhwa/manhua page. "
        "Output only the extracted text, preserving reading order. "
        "Include dialogue, narration, and sound effects. "
        "If no text is present, output an empty string."
    )
    
    response = httpx.post(
        f"{settings.ollama_url}/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "images": [base64.b64encode(image_bytes).decode()],
            "stream": False,
            "options": {"temperature": 0.0},
        },
        timeout=120.0,  # vision models can be slow
    )
    response.raise_for_status()
    return response.json().get("response", "").strip()
```

**Model selection:** Use `get_settings().default_chat` as the vision model. The `config.py` already has `default_chat: str = "qwen3:30b"`. If the model does not support vision, Ollama will return an error — log and treat as empty text.

**Ollama concurrency lock:** Add a module-level `threading.Lock` named `_ollama_lock` in `ocr_service.py`. Acquire it before the Ollama call and release after. This serializes all Ollama calls from the OCR service and prevents GPU memory exhaustion if future services also call Ollama concurrently.

### Image loading for archive chapters

Chapters can be stored as:
1. A folder of image files (`chapter.folder_path`, `page.file_path`)
2. A `.cbz` archive (`chapter.archive_path`, `page.file_path` is a relative path inside the archive)

```python
def _load_page_image(chapter: Chapter, page: Page) -> bytes:
    if chapter.archive_path:
        import zipfile
        with zipfile.ZipFile(chapter.archive_path, "r") as zf:
            return zf.read(page.file_path)
    else:
        return Path(page.file_path).read_bytes()
```

### `SeriesAiStatus` update

After each chapter completes, recalculate from `chapter_ocr_status` for that `series_id`:

```python
def _refresh_series_ai_status(series_id: int, db: Session) -> None:
    rows = db.query(ChapterOcrStatus).filter_by(series_id=series_id).all()
    total = len(rows)
    done = sum(1 for row in rows if row.status == "completed")
    pct = (done / total * 100) if total > 0 else 0.0

    status_row = db.query(SeriesAiStatus).filter_by(series_id=series_id).first()
    if status_row is None:
        status_row = SeriesAiStatus(series_id=series_id)
        db.add(status_row)
    
    status_row.ocr_chapters_done = done
    status_row.ocr_chapters_total = total
    status_row.ocr_pct = pct
    status_row.ocr_status = "completed" if done == total else ("partial" if done > 0 else "none")
    db.commit()
```

### FTS5 search

```python
def search_ocr_text(query: str, *, series_id: int | None = None, limit: int = 20, db: Session):
    sql = """
        SELECT
            ocr_pages.id,
            ocr_pages.page_id,
            ocr_pages.chapter_id,
            ocr_pages.series_id,
            snippet(ocr_pages_fts, 0, '<mark>', '</mark>', '…', 20) AS snippet,
            rank
        FROM ocr_pages_fts
        JOIN ocr_pages ON ocr_pages.id = ocr_pages_fts.rowid
        WHERE ocr_pages_fts MATCH :query
        {series_filter}
        ORDER BY rank
        LIMIT :limit
    """
    series_filter = "AND ocr_pages.series_id = :series_id" if series_id else ""
    params = {"query": query, "limit": limit}
    if series_id:
        params["series_id"] = series_id
    
    rows = db.execute(text(sql.format(series_filter=series_filter)), params).fetchall()
    return [dict(row._mapping) for row in rows]
```

**FTS5 query sanitization:** Wrap the user query in double quotes if it contains special characters: `query = f'"{query.replace(chr(34), "")}"'`.

---

## 7. REST Endpoints — `routes/ocr.py`

```
POST   /ocr/series/{series_id}/queue          Queue OCR for all chapters in a series
POST   /ocr/chapters/{chapter_id}/queue       Queue OCR for a single chapter
GET    /ocr/series/{series_id}/status         Series-level OCR progress
GET    /ocr/chapters/{chapter_id}/status      Chapter-level OCR status
GET    /ocr/series/{series_id}/search?q=...   FTS5 search within a series
GET    /tasks                                  List background tasks (paginated)
GET    /tasks/{task_id}                        Single task status
DELETE /tasks/{task_id}                        Cancel a pending or running task
```

### `POST /ocr/series/{series_id}/queue`

Request body (optional):
```json
{ "priority": 10 }
```

Response `202 Accepted`:
```json
{
  "queued": 47,
  "skipped": 3,
  "task_ids": [101, 102, 103, ...]
}
```

Behavior: load all chapters for the series, call `queue_chapter_ocr` for each, return count of queued vs. skipped (already completed).

### `GET /ocr/series/{series_id}/status`

Response `200`:
```json
{
  "series_id": 5,
  "ocr_status": "partial",
  "ocr_pct": 42.3,
  "ocr_chapters_done": 20,
  "ocr_chapters_total": 47,
  "chapters": [
    {
      "chapter_id": 101,
      "status": "completed",
      "ocr_pages_done": 72,
      "total_pages": 72
    }
  ]
}
```

### `GET /tasks`

Query params: `status=pending|running|completed|failed` (optional), `type=ocr_chapter` (optional), `page=1`, `per_page=50`

Response `200`:
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 50,
  "has_next": true
}
```

### `GET /tasks/{task_id}`

Response `200`:
```json
{
  "id": 101,
  "task_type": "ocr_chapter",
  "status": "running",
  "progress": 34.7,
  "priority": 100,
  "error": null,
  "created_at": "2026-07-01T10:00:00Z",
  "started_at": "2026-07-01T10:00:05Z",
  "finished_at": null
}
```

### `DELETE /tasks/{task_id}`

Cancels the task by setting `status = "cancelled"`. If the task is `running`, the handler must check for cancellation between pages — see the `_assert_can_continue` pattern in `DownloadManager`.

---

## 8. Integration with Library Import

**The problem:** The library scan must trigger OCR queuing after a successful import, but this agent must NOT modify `library_service.py`.

**The solution — event hook pattern:**

Add a module-level list to `library_service.py` (this is the ONLY allowed modification to that file):

```python
# At top of library_service.py, after imports:
_post_import_hooks: list[Callable[[int], None]] = []
# int = series_id

def register_post_import_hook(hook: Callable[[int], None]) -> None:
    _post_import_hooks.append(hook)
```

Then at the end of the `import_folder` method, after a successful import, call:
```python
for hook in _post_import_hooks:
    try:
        hook(series.id)
    except Exception:
        pass  # hooks must never fail the import
```

**The OCR service registers itself** in `main.py` lifespan (after `task_runner.start()`):

```python
from services.library_service import register_post_import_hook
from services.ocr_service import _on_series_imported

if get_settings().ocr_auto_queue:
    register_post_import_hook(_on_series_imported)
```

Where `_on_series_imported(series_id: int)` opens a new DB session and queues all chapters for OCR.

**Why `ocr_auto_queue` is disabled by default:** OCR requires a vision-capable model in Ollama. Not all users have one. The default `False` means no OCR jobs are ever queued until the user explicitly enables it or manually triggers via the API.

---

## 9. Data Flow

```
User triggers import (POST /library/import)
  │
  ├─ LibraryService.import_folder() scans and persists series/chapters/pages
  ├─ calls post_import_hooks if registered
  │     └─ _on_series_imported(series_id)
  │           └─ queue_chapter_ocr(chapter_id, priority=100) × N chapters
  │                 └─ INSERT background_tasks row
  │                 └─ INSERT chapter_ocr_status row
  │                 └─ TaskRunner.notify()
  │
  └─ Returns import response (unblocked — OCR is background)

TaskRunner (background thread, polling every 2s):
  ├─ SELECT next pending task ORDER BY priority, created_at
  ├─ Mark running
  ├─ handle_ocr_chapter_task(payload)
  │     ├─ Load pages
  │     ├─ For each page:
  │     │     ├─ Load image bytes
  │     │     ├─ _ollama_vision_ocr(bytes) → text
  │     │     ├─ Upsert OcrPage
  │     │     └─ FTS5 trigger fires automatically on INSERT/UPDATE
  │     ├─ Mark chapter_ocr_status completed
  │     └─ Refresh series_ai_status
  └─ Mark task completed

Frontend polls GET /ocr/series/{id}/status or GET /tasks/{id}
User searches GET /ocr/series/{id}/search?q=blade
```

---

## 10. Edge Cases

| Scenario | Behavior |
|---|---|
| OCR called twice for same chapter | `queue_chapter_ocr` is idempotent — returns existing task, no duplicate |
| Ollama is not running | `_ollama_vision_ocr` raises `httpx.ConnectError`. Page gets `text=None, confidence=0`. Chapter continues. After 50% failures, chapter marked failed. |
| Model does not support vision | Ollama returns error JSON. Same failure path as above. |
| Image file is missing/corrupt | `_load_page_image` raises. Same per-page failure path. |
| Archive (.cbz) is corrupt | `zipfile.BadZipFile` raised on open. Entire chapter marked failed, not retried automatically. |
| Task cancelled while running | Handler checks `BackgroundTask.status == "cancelled"` between each page. If detected, raises `CancelledError` and returns cleanly. |
| FTS5 trigger fails on INSERT | This is a SQLite error. Wrap FTS trigger population in try/except; if it fails, the page text is still in `ocr_pages` — search just won't find it. Log a warning. |
| Series has 0 pages (import incomplete) | `queue_chapter_ocr` checks `page_count > 0` before enqueuing. Skip with `status="skipped"` |
| OCR text is empty string | Valid result — some pages have no text (art-only pages). Store empty string, not NULL. |
| Task runner crashes | The daemon thread exits silently. The next startup calls `_recover_interrupted_tasks()` which resets any tasks stuck in `"running"` state back to `"pending"`. |

---

## 11. Error Handling

### Per-page errors (non-fatal)
- Log at `WARNING` level: `f"OCR failed for page {page.id}: {exc}"`
- Set `OcrPage.text = None`, `confidence = 0.0`
- Increment `ocr_pages_done` anyway (page was processed, just failed)
- Continue to next page

### Per-chapter threshold
- If `failed_pages / total_pages > 0.5`: mark `ChapterOcrStatus.status = "failed"`
- Set `ChapterOcrStatus.error = f"{failed_pages}/{total_pages} pages failed OCR"`

### Task runner errors
- Exception propagates out of `handle_ocr_chapter_task`
- `TaskRunner` catches it, sets `BackgroundTask.status = "failed"` with `error = str(exc)`
- Logs at `ERROR` level with full traceback

### Startup recovery
```python
def _recover_interrupted_tasks(db: Session) -> None:
    """Reset tasks stuck in 'running' state from a previous crash."""
    db.query(BackgroundTask).filter(
        BackgroundTask.status == "running"
    ).update({"status": "pending", "started_at": None, "worker_id": None})
    db.commit()
```
Call this at the start of `TaskRunner.start()`.

---

## 12. Performance Considerations

- **One Ollama call per page, serialized:** The `_ollama_lock` prevents concurrent GPU usage. OCR throughput ≈ 0.5 pages/second on a mid-range GPU (2 seconds/page). 72-page chapter ≈ 144 seconds ≈ 2.4 minutes per chapter. This is expected and acceptable.
- **Commit per page:** Committing after each page means a crash loses at most one page of work. Resume picks up from the last committed `OcrPage` row.
- **FTS5 triggers are synchronous:** Each `OcrPage` insert fires the FTS5 trigger in the same transaction. This adds ~1ms per insert. Negligible at single-page throughput.
- **`_refresh_series_ai_status` is a COUNT query:** Runs after every chapter. At 47 chapters, this queries 47 rows — trivial.
- **`search_ocr_text` with no series filter** searches ALL indexed text across the entire library. For the initial SQLite implementation this is acceptable. When the index grows past 100K pages, add a mandatory `series_id` filter or paginate more aggressively.
- **Memory:** Images are loaded one page at a time, encoded to base64, sent to Ollama, and released. No chapter's full image set is ever in memory simultaneously.

---

## 13. Security Considerations

- **Image path access:** `_load_page_image` reads from `page.file_path` which came from the library scanner. The scanner only stores paths within configured library roots. No user-supplied paths reach this function.
- **Ollama prompt injection:** The OCR prompt explicitly instructs the model to extract text only. The model's output is stored as raw text in `OcrPage.text` and served to Kimi Agent 2's intelligence layer. That layer must treat OCR text as untrusted user content when assembling LLM prompts.
- **FTS5 query sanitization:** User-supplied search queries are passed to FTS5 via parameterized SQL. The wrapping in quotes and escaping prevents FTS5 syntax injection (SQLite FTS5 uses its own query syntax; unescaped special characters like `*` `"` `(` cause query errors, not security issues, but proper escaping prevents user frustration).
- **No external network calls:** OCR is entirely local (Ollama on localhost). No data leaves the machine.

---

## 14. Testing Requirements

All tests go in `backend/tests/test_ocr.py` and `backend/tests/test_task_runner.py`.

### `test_task_runner.py`

```python
def test_task_runner_executes_registered_handler():
    # Register a test handler, enqueue a task, start runner briefly, verify handler was called

def test_task_runner_marks_task_failed_on_exception():
    # Register a handler that raises, verify task.status == "failed"

def test_claim_next_task_respects_priority():
    # Enqueue priority=100 and priority=10 tasks; verify priority=10 claimed first

def test_recover_interrupted_resets_running_tasks():
    # Create a task with status="running", call _recover_interrupted_tasks, verify status="pending"

def test_task_idempotency_does_not_duplicate():
    # Call queue_chapter_ocr twice with same chapter_id; verify only one task created
```

### `test_ocr.py`

```python
def test_queue_chapter_ocr_creates_task_and_status(db_session):
    # Create a chapter with pages, call queue_chapter_ocr, verify BackgroundTask and ChapterOcrStatus created

def test_queue_chapter_ocr_skips_completed_chapters(db_session):
    # Create a ChapterOcrStatus with status="completed", call queue_chapter_ocr, verify no new task

def test_search_ocr_text_finds_matching_pages(db_session):
    # Insert OcrPage with known text, call search_ocr_text, verify page is returned

def test_search_ocr_text_scoped_to_series(db_session):
    # Insert pages for two series, search scoped to series A, verify series B not in results

def test_handle_ocr_chapter_task_stores_text(db_session, monkeypatch):
    # Monkeypatch _ollama_vision_ocr to return "test text"
    # Monkeypatch _load_page_image to return fake bytes
    # Run handle_ocr_chapter_task
    # Verify OcrPage has text="test text" and chapter_ocr_status is "completed"

def test_handle_ocr_chapter_task_continues_on_page_failure(db_session, monkeypatch):
    # Monkeypatch _ollama_vision_ocr to raise on page 2 of 3
    # Verify pages 1 and 3 have text, page 2 has text=None
    # Verify chapter status is "completed" (1/3 failure rate < 50% threshold)

def test_series_ai_status_updated_after_chapter(db_session, monkeypatch):
    # After handle_ocr_chapter_task, verify SeriesAiStatus.ocr_pct is updated
```

---

## 15. Acceptance Criteria

- [ ] `pytest backend/tests/test_ocr.py` all pass
- [ ] `pytest backend/tests/test_task_runner.py` all pass
- [ ] Alembic migration applies cleanly on a fresh database
- [ ] Alembic migration downgrades cleanly
- [ ] `POST /ocr/series/{id}/queue` for a 47-chapter series enqueues 47 tasks
- [ ] Subsequent `POST /ocr/series/{id}/queue` on the same series enqueues 0 tasks (idempotent)
- [ ] `GET /tasks/{id}` shows correct progress as OCR runs
- [ ] `GET /ocr/series/{id}/status` shows `ocr_pct` increasing as chapters complete
- [ ] After OCR, `GET /ocr/series/{id}/search?q=blade` returns pages containing "blade"
- [ ] Server restart while OCR is running: tasks resume from last committed page on restart
- [ ] Ollama not running: OCR fails gracefully, task marked `failed`, server stays up
- [ ] Chapter with archive (`archive_path` set): images extracted correctly from zip
- [ ] TaskRunner daemon exits cleanly when `task_runner.stop()` is called
- [ ] No modifications made to `library_service.py` internals other than the hook registration lines

---

## 16. Merge Risks

**Risk 1 — `models.py`:** All four agents may touch this file. Protocol: append new classes after `SourceChapterLink`. Never edit above that line.

**Risk 2 — `main.py`:** TaskRunner startup goes inside `lifespan()`. Coordinate with Cursor Chat 2 (if they need lifespan changes for update polling) — both can coexist as separate lines in the same lifespan block.

**Risk 3 — `library_service.py`:** The hook pattern (`_post_import_hooks` list + `register_post_import_hook`) is the ONLY permitted modification to this file. If Cursor Chat 1 also touches this file for reader stability reasons, coordinate on which agent handles the hook addition.

**Risk 4 — `api/router.py`:** Append `include_router(ocr_router)` as the last line. Kimi Agent 2 will also append a line.

---

## 17. Future Extensibility

- **Summaries:** When Kimi Agent 2's intelligence layer runs, it calls `search_ocr_text` or reads `OcrPage.text_cleaned` directly. No changes to this spec needed.
- **Embeddings:** A future worker type `"embed_chapter"` registers its handler the same way as `"ocr_chapter"`. The `BackgroundTask` table and `TaskRunner` require no changes.
- **Concurrent workers:** The `TaskRunner` can be upgraded to a `ThreadPoolExecutor` by setting `max_concurrent > 1` once PostgreSQL's `SKIP LOCKED` is available.
- **Task scheduling:** The `scheduled_at` column on `BackgroundTask` already supports deferred execution — the poll query filters `scheduled_at IS NULL OR scheduled_at <= now()`.
- **Progress WebSocket:** `GET /tasks/{id}` is the polling endpoint. A future `WS /ws/tasks/{id}` endpoint can reuse the same `BackgroundTask` row for push updates.
