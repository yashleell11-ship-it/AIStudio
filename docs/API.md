# AIStudio — Complete API Contract

**Status:** Canonical reference. All route files must exactly match this document.
**Cross-references:** [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE.md](DATABASE.md) · [PROJECT_RULES.md](PROJECT_RULES.md)

---

## 1. Conventions

### Base URL

```
http://127.0.0.1:8000
```

No path versioning prefix. The API is consumed by a single client (the local frontend).
A version prefix will be introduced at a breaking-change boundary only.

### Authentication

**Phases 2–5:** None. The backend binds to `127.0.0.1` only.
**Phase 6:** Bearer JWT. `Authorization: Bearer <access_token>` on all protected routes.
Access tokens expire in 15 minutes; refresh tokens in 30 days.

### Error Envelope

Every non-2xx response uses this exact shape. Never deviate.

```json
{
  "code": "machine_readable_snake_case",
  "message": "Human readable description.",
  "details": { }
}
```

`details` is optional. Its structure is error-specific and documented per endpoint below.

### Pagination

List endpoints accept:

| Query param | Type | Default | Description |
|-------------|------|---------|-------------|
| `page` | integer ≥ 1 | `1` | Page number |
| `per_page` | integer 1–200 | `40` | Items per page |

All list responses share this wrapper:

```json
{
  "items": [ ... ],
  "total": 1000,
  "page": 1,
  "per_page": 40,
  "has_next": true
}
```

### Timestamps

All timestamps are ISO 8601 UTC strings: `"2024-01-15T10:30:00Z"`.
Nullable timestamps are `null` in JSON when unset.

### Image URLs

Image-serving endpoints return binary data directly (not JSON).
References to images in JSON payloads use a relative URL path string
(e.g., `"/library/covers/series/1"`) that the frontend resolves to an absolute URL.

---

## 2. Common Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| `not_found` | 404 | Generic: resource does not exist |
| `series_not_found` | 404 | Series ID does not exist |
| `chapter_not_found` | 404 | Chapter ID does not exist |
| `page_not_found` | 404 | Page ID does not exist |
| `library_not_found` | 404 | Library root ID does not exist |
| `collection_not_found` | 404 | Collection ID does not exist |
| `tag_not_found` | 404 | Tag ID does not exist |
| `character_not_found` | 404 | Character ID does not exist |
| `path_not_found` | 400 | Provided file system path does not exist |
| `path_outside_library` | 403 | Path is not under any registered library root |
| `path_already_imported` | 409 | Path is already registered as a library root |
| `import_in_progress` | 409 | A scan is already running for this library |
| `image_file_missing` | 404 | Page was indexed but file no longer exists on disk |
| `archive_read_error` | 500 | CBZ/CBR extraction failed |
| `ollama_unavailable` | 503 | Ollama process is not running or not reachable |
| `model_not_found` | 404 | Requested model is not loaded in Ollama |
| `ocr_not_complete` | 409 | Operation requires OCR that has not yet run |
| `embeddings_not_ready` | 409 | Operation requires embeddings that are not yet built |
| `validation_error` | 422 | Request body failed schema validation |
| `task_not_found` | 404 | Background task ID does not exist |
| `task_not_cancellable` | 409 | Task is already complete or failed |
| `internal_error` | 500 | Unexpected server error |

---

## 3. System Endpoints

### `GET /`

Returns basic service status. Used by the frontend health check on startup.

**Response 200**
```json
{
  "status": "ok",
  "name": "AIStudio",
  "version": "0.1.0"
}
```

---

### `GET /health`

Returns detailed component status. Used by the Settings UI health panel.

**Response 200**
```json
{
  "status": "ok",
  "database": "ok",
  "ollama": "ok",
  "comfyui": "unavailable",
  "disk_free_gb": 234.5,
  "library_count": 2,
  "series_count": 1247,
  "chapter_count": 84203
}
```

`ollama` and `comfyui` are `"ok"` | `"unavailable"`. Other fields are always present.

---

## 4. Settings Endpoints

### `GET /settings`

Returns all user preferences stored in the `settings` table.

**Response 200**
```json
{
  "reader.default_mode": "webtoon",
  "reader.zoom_level": 1.0,
  "reader.prefetch_pages": 10,
  "reader.reading_direction": "ltr",
  "reader.double_page_mode": false,
  "library.default_sort": "last_read",
  "library.default_filter": "all",
  "library.grid_columns": 6,
  "ai.auto_ocr_on_import": false,
  "ai.auto_embed_after_ocr": true,
  "ai.auto_summarize_after_embed": false,
  "ai.spoiler_gate_enabled": true,
  "ui.sidebar_collapsed": false
}
```

---

### `PATCH /settings`

Updates one or more settings keys.

**Request body**
```json
{
  "reader.default_mode": "manga",
  "library.grid_columns": 4
}
```

Unknown keys are rejected. Values are JSON-typed (string, number, boolean).

**Response 200** — same shape as `GET /settings` (full updated settings object).

**Errors:** `validation_error` if a key is unknown or value has the wrong type.

---

## 5. Library: Roots

### `GET /library/roots`

Returns all registered library root paths.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "name": "Main Library",
      "root_path": "D:/Manhwa",
      "is_active": true,
      "scan_interval_minutes": 60,
      "last_scanned_at": "2024-01-15T08:00:00Z",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

### `POST /library/roots`

Register a new library root path.

**Request body**
```json
{
  "name": "NAS Library",
  "root_path": "E:/NAS/Manhwa",
  "scan_interval_minutes": 120
}
```

`name` required. `root_path` required. `scan_interval_minutes` optional (default 60).

**Response 201**
```json
{
  "id": 2,
  "name": "NAS Library",
  "root_path": "E:/NAS/Manhwa",
  "is_active": true,
  "scan_interval_minutes": 120,
  "last_scanned_at": null,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Errors:** `path_not_found`, `path_already_imported`, `validation_error`.

---

### `DELETE /library/roots/{id}`

Remove a library root. All series, chapters, and pages under this root are
soft-deleted. Reading progress and AI data are preserved.

**Response 204** — no body.

**Errors:** `library_not_found`.

---

### `POST /library/roots/{id}/scan`

Trigger an immediate rescan of a library root.

**Request body** — empty `{}` or omitted.

**Response 202**
```json
{
  "task_id": 42,
  "message": "Scan started."
}
```

Use `GET /tasks/42` to poll progress, or `WS /ws/tasks/42` to stream it.

**Errors:** `library_not_found`, `import_in_progress`.

---

## 6. Library: Series

### `GET /library/series`

Paginated, filterable, sortable series list. The primary library endpoint.

**Query parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `per_page` | int | 40 | Items per page (max 200) |
| `sort` | string | `sort_title` | `sort_title` \| `last_read` \| `date_added` \| `author` \| `year` \| `total_chapters` |
| `order` | string | `asc` | `asc` \| `desc` |
| `reading_status` | string | — | `unread` \| `reading` \| `completed` \| `on_hold` \| `dropped` \| `plan_to_read` |
| `collection_id` | int | — | Filter to a collection |
| `tag_id` | int | — | Filter to a tag |
| `library_id` | int | — | Filter to a library root |
| `is_favorite` | bool | — | `true` to show favorites only |
| `language` | string | — | ISO 639-1 code |
| `q` | string | — | Quick title/author search (FTS, always available) |

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "title": "Solo Leveling",
      "sort_title": "solo leveling",
      "original_title": "나 혼자만 레벨업",
      "author": "Chugong",
      "artist": "Dubu",
      "description": "In a world where hunters...",
      "status": "completed",
      "content_rating": "safe",
      "language": "ko",
      "year": 2018,
      "cover_url": "/library/covers/series/1",
      "reading_status": "reading",
      "is_favorite": false,
      "total_chapters": 179,
      "read_chapters": 45,
      "total_pages": 12853,
      "is_created": false,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 1247,
  "page": 1,
  "per_page": 40,
  "has_next": true
}
```

---

### `GET /library/series/{id}`

Full series detail including chapter list and reading progress.

**Response 200**
```json
{
  "id": 1,
  "library_id": 1,
  "title": "Solo Leveling",
  "sort_title": "solo leveling",
  "original_title": "나 혼자만 레벨업",
  "author": "Chugong",
  "artist": "Dubu",
  "description": "...",
  "status": "completed",
  "content_rating": "safe",
  "language": "ko",
  "year": 2018,
  "cover_url": "/library/covers/series/1",
  "reading_status": "reading",
  "is_favorite": false,
  "total_chapters": 179,
  "read_chapters": 45,
  "total_pages": 12853,
  "is_created": false,
  "tags": [
    { "id": 3, "name": "Action", "category": "genre", "color": "#ff6b6b" }
  ],
  "collections": [
    { "id": 1, "name": "Favorites" }
  ],
  "reading_progress": {
    "current_chapter_id": 23,
    "current_page": 14,
    "scroll_offset_px": 3200,
    "progress_pct": 25.1,
    "started_at": "2024-01-10T09:00:00Z",
    "last_read_at": "2024-01-15T22:00:00Z"
  },
  "ai_status": {
    "ocr_pct": 100.0,
    "embed_pct": 100.0,
    "summary_pct": 100.0,
    "knowledge_extracted_at": "2024-01-14T12:00:00Z"
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

**Errors:** `series_not_found`.

---

### `GET /library/series/{id}/chapters`

Ordered chapter list for a series.

**Query parameters:** `page`, `per_page` (default 200 — most chapter lists fit one page).

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "volume_id": null,
      "title": "Chapter 1 — The World's Weakest Hunter",
      "number": 1.0,
      "sort_key": "0001.000",
      "source_type": "folder",
      "page_count": 72,
      "cover_url": "/library/covers/chapter/1",
      "is_read": false,
      "read_at": null,
      "scanned_at": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 179,
  "page": 1,
  "per_page": 200,
  "has_next": false
}
```

**Errors:** `series_not_found`.

---

### `PATCH /library/series/{id}`

Update series metadata. Used by the metadata editor UI.
Only fields present in the request body are updated.

**Request body** (all fields optional)
```json
{
  "title": "Solo Leveling",
  "author": "Chugong",
  "artist": "Dubu",
  "description": "...",
  "status": "completed",
  "content_rating": "safe",
  "language": "ko",
  "year": 2018,
  "reading_status": "reading",
  "is_favorite": true
}
```

**Enumerated values:**
- `status`: `ongoing` | `completed` | `hiatus` | `cancelled` | `unknown`
- `content_rating`: `safe` | `suggestive` | `adult` | `unknown`
- `reading_status`: `unread` | `reading` | `completed` | `on_hold` | `dropped` | `plan_to_read`

**Response 200** — full series object (same as `GET /library/series/{id}`).

**Errors:** `series_not_found`, `validation_error`.

---

### `DELETE /library/series/{id}`

Soft-delete a series. Sets `deleted_at`; does not remove from disk.
Reading progress and AI data are preserved.

**Response 204** — no body.

**Errors:** `series_not_found`.

---

### `GET /library/series/{id}/volumes`

Volume list for a series.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "number": 1.0,
      "title": "Volume 1",
      "cover_url": "/library/covers/volume/1",
      "chapter_count": 10
    }
  ],
  "total": 19
}
```

**Errors:** `series_not_found`.

---

### `POST /library/import`

Start a background library scan. Accepts a folder path or a library root ID.

**Request body**
```json
{
  "path": "D:/Manhwa/Solo Leveling",
  "library_id": 1
}
```

`library_id` required. `path` optional — if omitted, scans the full library root.

**Response 202**
```json
{
  "task_id": 42,
  "message": "Import started."
}
```

**Errors:** `library_not_found`, `path_not_found`, `path_outside_library`, `import_in_progress`.

---

### `GET /library/covers/series/{id}`

Serve the cover image for a series.

**Response 200** — binary image data.

| Header | Value |
|--------|-------|
| `Content-Type` | `image/jpeg` |
| `Cache-Control` | `max-age=86400, immutable` |

**Errors:** `series_not_found`, `image_file_missing` (returns a placeholder cover image).

---

### `GET /library/covers/chapter/{id}`

Serve the cover image for a chapter.

**Response 200** — binary image data (same headers as series cover).

**Errors:** `chapter_not_found`, `image_file_missing`.

---

## 7. Library: Chapters and Pages

### `GET /library/chapters/{id}`

Chapter detail with ordered page list.

**Response 200**
```json
{
  "id": 1,
  "series_id": 1,
  "volume_id": null,
  "title": "Chapter 1",
  "number": 1.0,
  "sort_key": "0001.000",
  "source_type": "folder",
  "page_count": 72,
  "cover_url": "/library/covers/chapter/1",
  "file_size_bytes": 38291456,
  "is_read": false,
  "read_at": null,
  "pages": [
    {
      "id": 100001,
      "page_number": 1,
      "image_url": "/reader/pages/100001/image",
      "width": 800,
      "height": 1200,
      "mime_type": "image/jpeg"
    }
  ],
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Errors:** `chapter_not_found`.

---

### `POST /library/chapters/{id}/mark-read`

Mark a chapter as read or unread.

**Request body**
```json
{ "is_read": true }
```

**Response 200**
```json
{ "id": 1, "is_read": true, "read_at": "2024-01-15T22:00:00Z" }
```

**Errors:** `chapter_not_found`.

---

## 8. Library: Collections

### `GET /library/collections`

All collections.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "name": "Gate-style Isekai",
      "description": "Series with hunters entering dungeons",
      "cover_url": "/library/covers/series/1",
      "series_count": 12,
      "sort_order": 0,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 5
}
```

---

### `POST /library/collections`

Create a collection.

**Request body**
```json
{
  "name": "Art Study References",
  "description": "Series with exceptional art for study"
}
```

**Response 201**
```json
{
  "id": 2,
  "name": "Art Study References",
  "description": "Series with exceptional art for study",
  "cover_url": null,
  "series_count": 0,
  "sort_order": 0,
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Errors:** `validation_error` (name must be unique).

---

### `GET /library/collections/{id}`

Collection detail with series list.

**Query parameters:** `page`, `per_page`.

**Response 200**
```json
{
  "id": 1,
  "name": "Gate-style Isekai",
  "description": "...",
  "cover_url": null,
  "sort_order": 0,
  "created_at": "2024-01-01T00:00:00Z",
  "series": {
    "items": [ /* SeriesSummary objects */ ],
    "total": 12,
    "page": 1,
    "per_page": 40,
    "has_next": false
  }
}
```

**Errors:** `collection_not_found`.

---

### `PATCH /library/collections/{id}`

Update collection metadata.

**Request body** (all optional)
```json
{ "name": "...", "description": "...", "sort_order": 1 }
```

**Response 200** — full collection object.

**Errors:** `collection_not_found`, `validation_error`.

---

### `DELETE /library/collections/{id}`

Delete a collection. Series within it are not deleted.

**Response 204**.

**Errors:** `collection_not_found`.

---

### `POST /library/collections/{id}/series/{series_id}`

Add a series to a collection.

**Response 200**
```json
{ "collection_id": 1, "series_id": 4, "added_at": "2024-01-15T10:30:00Z" }
```

**Errors:** `collection_not_found`, `series_not_found`.

---

### `DELETE /library/collections/{id}/series/{series_id}`

Remove a series from a collection.

**Response 204**.

**Errors:** `collection_not_found`, `series_not_found`.

---

## 9. Library: Tags

### `GET /library/tags`

All tags, with optional category filter.

**Query parameters:** `category` (optional).

**Response 200**
```json
{
  "items": [
    { "id": 1, "name": "Action", "category": "genre", "color": "#ff6b6b", "series_count": 234 }
  ],
  "total": 87
}
```

---

### `POST /library/tags`

Create a tag.

**Request body**
```json
{ "name": "System", "category": "theme", "color": "#6366f1" }
```

**Response 201** — full tag object.

**Errors:** `validation_error` (name must be unique).

---

### `DELETE /library/tags/{id}`

Delete a tag and all its series associations.

**Response 204**.

**Errors:** `tag_not_found`.

---

### `POST /library/series/{id}/tags`

Add a tag to a series.

**Request body**
```json
{ "tag_id": 3 }
```

**Response 200**
```json
{ "series_id": 1, "tag_id": 3, "is_ai_generated": false }
```

**Errors:** `series_not_found`, `tag_not_found`.

---

### `DELETE /library/series/{id}/tags/{tag_id}`

Remove a tag from a series.

**Response 204**.

**Errors:** `series_not_found`, `tag_not_found`.

---

## 10. Reader Endpoints

### `GET /reader/chapters/{id}`

Returns full chapter with ordered page list for the reader.
Identical to `GET /library/chapters/{id}` but also returns chapter progress.

**Response 200**
```json
{
  "id": 1,
  "series_id": 1,
  "title": "Chapter 1",
  "number": 1.0,
  "source_type": "folder",
  "page_count": 72,
  "pages": [
    {
      "id": 100001,
      "page_number": 1,
      "image_url": "/reader/pages/100001/image",
      "width": 800,
      "height": 1200,
      "mime_type": "image/jpeg"
    }
  ],
  "prev_chapter_id": null,
  "next_chapter_id": 2,
  "progress": {
    "last_page": 14,
    "scroll_offset_px": 3200,
    "is_completed": false,
    "time_spent_seconds": 840
  }
}
```

**Errors:** `chapter_not_found`.

---

### `GET /reader/pages/{id}/image`

Serve a single page image. This is the hot path — called for every page load.

For folder-type chapters: `FileResponse` from disk.
For CBZ/CBR chapters: `StreamingResponse` from archive extraction.
For PDF chapters: `StreamingResponse` from page render.

**Response 200** — binary image data.

| Header | Value |
|--------|-------|
| `Content-Type` | `image/jpeg` \| `image/png` \| `image/webp` |
| `Cache-Control` | `max-age=604800, immutable` (7 days) |
| `ETag` | SHA-256 hash of image data |

**Errors:** `page_not_found`, `image_file_missing`, `archive_read_error`.

---

### `GET /reader/series/{id}/progress`

Get the resume point for a series. Used by "Continue Reading" on the Library page.

**Response 200**
```json
{
  "series_id": 1,
  "current_chapter_id": 23,
  "current_page": 14,
  "scroll_offset_px": 3200,
  "progress_pct": 25.1,
  "started_at": "2024-01-10T09:00:00Z",
  "last_read_at": "2024-01-15T22:00:00Z"
}
```

Returns `null` for all fields except `series_id` when no reading has started.

**Errors:** `series_not_found`.

---

### `POST /reader/progress`

Save reading progress. Called every 5 pages and on chapter close.

**Request body**
```json
{
  "series_id": 1,
  "chapter_id": 23,
  "page": 14,
  "scroll_offset_px": 3200,
  "time_spent_seconds_delta": 60
}
```

`time_spent_seconds_delta` is added to the chapter's accumulated time.

**Response 200**
```json
{
  "series_progress_pct": 25.1,
  "chapter_is_completed": false
}
```

**Errors:** `series_not_found`, `chapter_not_found`.

---

### `GET /reader/series/{id}/next-chapter`

Returns the next unread chapter for "Continue Reading" and end-of-chapter navigation.

**Response 200**
```json
{ "chapter_id": 24, "chapter_number": 24.0, "title": "Chapter 24" }
```

Returns `{ "chapter_id": null }` when the series is complete.

**Errors:** `series_not_found`.

---

## 11. Bookmarks

### `GET /reader/series/{id}/bookmarks`

All bookmarks for a series.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "chapter_id": 23,
      "page_id": 100050,
      "page_number": 14,
      "note": "The awakening scene",
      "created_at": "2024-01-15T22:00:00Z"
    }
  ],
  "total": 5
}
```

**Errors:** `series_not_found`.

---

### `POST /reader/bookmarks`

Create a bookmark.

**Request body**
```json
{
  "series_id": 1,
  "chapter_id": 23,
  "page_id": 100050,
  "page_number": 14,
  "note": "The awakening scene"
}
```

**Response 201** — full bookmark object.

**Errors:** `series_not_found`, `chapter_not_found`, `page_not_found`, `validation_error`.

---

### `DELETE /reader/bookmarks/{id}`

Delete a bookmark.

**Response 204**.

**Errors:** `not_found`.

---

## 12. Search

### `GET /search`

Unified search across all content types. Supports FTS (Phase 2) and semantic (Phase 3).

**Query parameters**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | yes | Search query |
| `type` | string | no | `all` \| `series` \| `chapter` \| `character` \| `scene` (default `all`) |
| `series_id` | int | no | Restrict to a single series |
| `semantic` | bool | no | `true` = semantic + FTS; `false` = FTS only (default `false`) |
| `page` | int | no | 1 |
| `per_page` | int | no | 20 |

**Response 200**
```json
{
  "query": "the chapter where jin-woo awakens",
  "semantic": true,
  "results": {
    "series": [
      {
        "id": 1,
        "title": "Solo Leveling",
        "cover_url": "/library/covers/series/1",
        "match_snippet": "...Jin-woo awakened as the Shadow Monarch..."
      }
    ],
    "chapters": [
      {
        "id": 14,
        "series_id": 1,
        "series_title": "Solo Leveling",
        "title": "Chapter 14",
        "number": 14.0,
        "cover_url": "/library/covers/chapter/14",
        "match_snippet": "...he felt the system awaken within him...",
        "similarity_score": 0.921
      }
    ],
    "characters": [],
    "scenes": []
  },
  "total": 3
}
```

**Errors:** `validation_error` (empty query), `embeddings_not_ready` (semantic=true but no embeddings exist).

---

### `GET /search/series`

Series-only FTS search. Optimized for the Library quick-search bar.
Always uses FTS; does not support semantic.

**Query parameters:** `q` (required), `page`, `per_page`.

**Response 200** — `{ items: SeriesSummary[], total, page, per_page, has_next }`.

---

### `GET /search/ocr`

Search inside panel dialogue via FTS5 over the `ocr_pages` table.

**Query parameters**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | yes | Dialogue text to find |
| `series_id` | int | no | Restrict to one series |
| `page` | int | no | 1 |
| `per_page` | int | no | 20 |

**Response 200**
```json
{
  "items": [
    {
      "page_id": 100050,
      "chapter_id": 14,
      "series_id": 1,
      "page_number": 7,
      "match_snippet": "...I will become stronger than anyone...",
      "image_url": "/reader/pages/100050/image"
    }
  ],
  "total": 8,
  "page": 1,
  "per_page": 20,
  "has_next": false
}
```

**Errors:** `ocr_not_complete` (no OCR text indexed at all).

---

### `GET /search/semantic`

Pure semantic search over all embedding chunks.

**Query parameters:** `q` (required), `series_id` (optional), `page`, `per_page`.

**Response 200** — same shape as `/search/ocr` results, plus `similarity_score` on each item.

**Errors:** `embeddings_not_ready`.

---

## 13. AI: Analysis Pipeline

### `POST /ai/analyze/{series_id}`

Trigger the full AI analysis pipeline for a series.
Queues OCR → Embed → Summarize → Extract in sequence.

**Request body** (all optional)
```json
{
  "force_rerun": false,
  "stages": ["ocr", "embed", "summarize", "knowledge"]
}
```

`stages` defaults to all. `force_rerun` re-runs stages even if already complete.

**Response 202**
```json
{
  "task_ids": {
    "ocr": 101,
    "embed": 102,
    "summarize": 103,
    "knowledge": 104
  },
  "message": "Analysis pipeline queued."
}
```

**Errors:** `series_not_found`, `ollama_unavailable`.

---

### `GET /ai/analyze/{series_id}/status`

Current AI analysis pipeline status for a series.

**Response 200**
```json
{
  "series_id": 1,
  "ocr": {
    "pct": 100.0,
    "pages_done": 12853,
    "pages_total": 12853,
    "completed_at": "2024-01-14T06:00:00Z"
  },
  "embed": {
    "pct": 100.0,
    "chunks_done": 24100,
    "chunks_total": 24100,
    "completed_at": "2024-01-14T07:30:00Z"
  },
  "summarize": {
    "pct": 100.0,
    "chapters_done": 179,
    "chapters_total": 179,
    "completed_at": "2024-01-14T08:15:00Z"
  },
  "knowledge": {
    "pct": 100.0,
    "extracted_at": "2024-01-14T09:00:00Z"
  }
}
```

**Errors:** `series_not_found`.

---

### `POST /ai/ocr/chapter/{chapter_id}`

Queue OCR for a single chapter.

**Request body**
```json
{ "force_rerun": false }
```

**Response 202**
```json
{ "task_id": 101, "message": "OCR queued for chapter." }
```

**Errors:** `chapter_not_found`, `ollama_unavailable`.

---

### `GET /ai/ocr/chapter/{chapter_id}/status`

OCR completion status for a chapter.

**Response 200**
```json
{
  "chapter_id": 14,
  "total_pages": 72,
  "ocr_pages_done": 72,
  "is_complete": true,
  "model": "minicpm-v:8b"
}
```

**Errors:** `chapter_not_found`.

---

### `GET /ai/ocr/page/{page_id}`

Get the OCR text for a single page.

**Response 200**
```json
{
  "page_id": 100050,
  "text_content": "System: You have been selected as a Player...",
  "confidence": 0.94,
  "language_detected": "en",
  "model": "minicpm-v:8b",
  "word_count": 42
}
```

Returns `{ "text_content": null }` if this page has not been OCR'd.

**Errors:** `page_not_found`.

---

## 14. AI: Summaries

### `GET /ai/summaries/series/{series_id}`

Get all summaries for a series (series-level and all chapters).

**Query parameters:** `type` — `chapter` | `series` | `all` (default `all`).

**Response 200**
```json
{
  "series_summary": {
    "id": 1,
    "summary_type": "series",
    "content": "Solo Leveling follows Sung Jin-woo...",
    "model": "llama3.3:70b",
    "is_user_edited": false,
    "word_count": 245,
    "updated_at": "2024-01-14T08:15:00Z"
  },
  "chapter_summaries": [
    {
      "id": 10,
      "chapter_id": 1,
      "summary_type": "chapter",
      "content": "Jin-woo enters the double dungeon...",
      "model": "llama3.3:70b",
      "is_user_edited": false,
      "word_count": 85,
      "has_spoilers": false,
      "updated_at": "2024-01-14T08:00:00Z"
    }
  ]
}
```

**Errors:** `series_not_found`.

---

### `GET /ai/summaries/chapter/{chapter_id}`

Single chapter summary.

**Response 200** — single summary object (same shape as chapter_summaries item above).

Returns `{ "summary": null }` if no summary exists yet.

**Errors:** `chapter_not_found`.

---

### `PUT /ai/summaries/{id}`

Update summary content (user editing AI output).
Sets `is_user_edited = true`.

**Request body**
```json
{ "content": "My corrected summary..." }
```

**Response 200** — full summary object.

**Errors:** `not_found`, `validation_error`.

---

### `POST /ai/summaries/series/{series_id}/generate`

Regenerate summaries for all chapters (or specific chapters).

**Request body**
```json
{
  "chapter_ids": [1, 2, 3],
  "force_rerun": false,
  "preserve_user_edits": true
}
```

`chapter_ids` optional — omit to regenerate all. `preserve_user_edits` (default `true`)
skips chapters where `is_user_edited = true`.

**Response 202**
```json
{ "task_id": 103, "chapters_queued": 179 }
```

**Errors:** `series_not_found`, `ocr_not_complete`, `ollama_unavailable`.

---

## 15. AI: Chat

### `GET /ai/chat/series/{series_id}/sessions`

All chat sessions for a series.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "title": "Power system explanation",
      "model": "qwen3:30b",
      "context_chapter_id": null,
      "message_count": 12,
      "is_archived": false,
      "created_at": "2024-01-14T20:00:00Z",
      "updated_at": "2024-01-14T20:30:00Z"
    }
  ],
  "total": 3
}
```

**Errors:** `series_not_found`.

---

### `POST /ai/chat/sessions`

Create a new chat session.

**Request body**
```json
{
  "series_id": 1,
  "title": "Who is the strongest hunter?",
  "context_chapter_id": 100
}
```

`context_chapter_id` sets the spoiler gate — AI only uses content up to this chapter.
Omit to give AI access to the full series.

**Response 201**
```json
{
  "id": 2,
  "series_id": 1,
  "title": "Who is the strongest hunter?",
  "model": "qwen3:30b",
  "context_chapter_id": 100,
  "is_archived": false,
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Errors:** `series_not_found`, `chapter_not_found`, `ocr_not_complete`, `ollama_unavailable`.

---

### `POST /ai/chat/sessions/{id}/messages`

Send a message and stream the AI response.

**Request body**
```json
{ "content": "Explain the Shadow Monarch power system." }
```

**Response 200** — `text/event-stream` (Server-Sent Events).

Each event is a JSON chunk:
```
data: {"delta": "The Shadow "}
data: {"delta": "Monarch power "}
data: {"delta": "system..."}
data: {"done": true, "tokens_used": 342, "message_id": 48}
```

On error during streaming:
```
data: {"error": true, "code": "ollama_unavailable", "message": "Ollama stopped responding."}
```

**Errors (pre-stream):** `not_found`, `ollama_unavailable`, `validation_error`.

---

### `GET /ai/chat/sessions/{id}/messages`

Full message history for a session.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "session_id": 1,
      "role": "user",
      "content": "Explain the Shadow Monarch power system.",
      "model": null,
      "tokens_used": null,
      "created_at": "2024-01-15T10:00:00Z"
    },
    {
      "id": 2,
      "session_id": 1,
      "role": "assistant",
      "content": "The Shadow Monarch is...",
      "model": "qwen3:30b",
      "tokens_used": 342,
      "created_at": "2024-01-15T10:00:05Z"
    }
  ],
  "total": 12
}
```

**Errors:** `not_found`.

---

### `DELETE /ai/chat/sessions/{id}`

Delete a chat session and all its messages.

**Response 204**.

**Errors:** `not_found`.

---

## 16. AI: Metadata Extraction

### `POST /ai/metadata/series/{series_id}/extract`

Queue AI metadata extraction: tags, description, genre classification.

**Request body**
```json
{ "force_rerun": false }
```

**Response 202**
```json
{ "task_id": 104, "message": "Metadata extraction queued." }
```

**Errors:** `series_not_found`, `ocr_not_complete`, `ollama_unavailable`.

---

## 17. Knowledge Graph: Characters

### `GET /knowledge/series/{series_id}/characters`

All characters in a series.

**Query parameters:** `page`, `per_page`, `role` (optional: `protagonist|antagonist|supporting|minor|unknown`).

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "name": "Sung Jin-woo",
      "role": "protagonist",
      "description": "The weakest E-rank hunter who...",
      "appearance": "Black hair, grey eyes...",
      "personality": "Determined, strategic...",
      "abilities": "Shadow Monarch powers, ruler's authority...",
      "arc_summary": "Goes from weakest to strongest...",
      "cover_url": "/library/covers/character/1",
      "aliases": ["Shadow Monarch", "Ant King Slayer"],
      "is_ai_generated": true,
      "is_user_edited": false,
      "created_at": "2024-01-14T09:00:00Z"
    }
  ],
  "total": 87
}
```

**Errors:** `series_not_found`.

---

### `POST /knowledge/characters`

Create a character manually.

**Request body**
```json
{
  "series_id": 1,
  "name": "Sung Jin-woo",
  "role": "protagonist",
  "description": "...",
  "aliases": ["Shadow Monarch"]
}
```

**Response 201** — full character object.

**Errors:** `series_not_found`, `validation_error`.

---

### `GET /knowledge/characters/{id}`

Single character with full profile.

**Response 200** — full character object (same shape as list item).

**Errors:** `character_not_found`.

---

### `PATCH /knowledge/characters/{id}`

Update character profile. Sets `is_user_edited = true`.

**Request body** (all optional)
```json
{
  "name": "Sung Jin-woo",
  "role": "protagonist",
  "description": "...",
  "appearance": "...",
  "personality": "...",
  "abilities": "...",
  "arc_summary": "..."
}
```

**Response 200** — full character object.

**Errors:** `character_not_found`, `validation_error`.

---

### `DELETE /knowledge/characters/{id}`

Delete a character and all their appearances and relationships.

**Response 204**.

**Errors:** `character_not_found`.

---

### `GET /knowledge/characters/{id}/appearances`

Chapters and pages where a character appears.

**Query parameters:** `page`, `per_page`.

**Response 200**
```json
{
  "items": [
    {
      "chapter_id": 1,
      "chapter_number": 1.0,
      "chapter_title": "Chapter 1",
      "page_number": 5,
      "image_url": "/reader/pages/100005/image",
      "context_note": "First appearance"
    }
  ],
  "total": 172
}
```

**Errors:** `character_not_found`.

---

### `GET /knowledge/series/{series_id}/relationships`

All character relationships in a series (graph data).

**Response 200**
```json
{
  "nodes": [
    { "id": 1, "name": "Sung Jin-woo", "role": "protagonist", "cover_url": "..." }
  ],
  "edges": [
    {
      "id": 1,
      "character_a_id": 1,
      "character_b_id": 2,
      "relationship_type": "ally",
      "description": "Childhood friends who fight together",
      "is_user_edited": false
    }
  ]
}
```

**Errors:** `series_not_found`.

---

### `POST /knowledge/relationships`

Create a character relationship.

**Request body**
```json
{
  "series_id": 1,
  "character_a_id": 1,
  "character_b_id": 2,
  "relationship_type": "ally",
  "description": "..."
}
```

The service normalizes `character_a_id < character_b_id` before inserting.

**Response 201** — full relationship object.

**Errors:** `series_not_found`, `character_not_found`, `validation_error`.

---

### `PATCH /knowledge/relationships/{id}`

Update a relationship. Sets `is_user_edited = true`.

**Request body**
```json
{ "relationship_type": "rival", "description": "..." }
```

**Response 200** — full relationship object.

**Errors:** `not_found`, `validation_error`.

---

### `DELETE /knowledge/relationships/{id}`

Delete a relationship.

**Response 204**.

**Errors:** `not_found`.

---

## 18. Knowledge Graph: Timeline

### `GET /knowledge/series/{series_id}/timeline`

Ordered timeline events for a series.

**Query parameters:** `include_spoilers` (bool, default `false`).

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "title": "System Awakening",
      "description": "Jin-woo survives the double dungeon and receives the System",
      "event_type": "story",
      "sequence_order": 14.0,
      "chapter_id": 14,
      "page_number": 68,
      "characters": [
        { "id": 1, "name": "Sung Jin-woo", "role": "actor" }
      ],
      "is_spoiler": false,
      "is_user_edited": false,
      "created_at": "2024-01-14T09:00:00Z"
    }
  ],
  "total": 340
}
```

**Errors:** `series_not_found`.

---

### `POST /knowledge/series/{series_id}/timeline/generate`

Queue AI timeline generation from chapter summaries.

**Request body**
```json
{ "force_rerun": false }
```

**Response 202**
```json
{ "task_id": 105, "message": "Timeline generation queued." }
```

**Errors:** `series_not_found`, `ocr_not_complete`, `ollama_unavailable`.

---

### `POST /knowledge/timeline/events`

Create a timeline event manually.

**Request body**
```json
{
  "series_id": 1,
  "title": "System Awakening",
  "description": "...",
  "event_type": "story",
  "sequence_order": 14.0,
  "chapter_id": 14,
  "page_number": 68,
  "character_ids": [1]
}
```

**Response 201** — full event object.

**Errors:** `series_not_found`, `chapter_not_found`, `character_not_found`, `validation_error`.

---

### `PATCH /knowledge/timeline/events/{id}`

Update a timeline event. Sets `is_user_edited = true`.

**Request body** — any event fields (all optional).

**Response 200** — full event object.

**Errors:** `not_found`, `validation_error`.

---

### `DELETE /knowledge/timeline/events/{id}`

Delete a timeline event.

**Response 204**.

**Errors:** `not_found`.

---

## 19. Knowledge Graph: World

### `GET /knowledge/series/{series_id}/world`

Full world data for a series (locations, factions, lore).

**Response 200**
```json
{
  "locations": [
    {
      "id": 1,
      "name": "Jeju Island S-Rank Gate",
      "description": "The most dangerous dungeon on the Korean peninsula",
      "location_type": "dungeon",
      "parent_id": null,
      "children": [],
      "first_appears_chapter_id": 100,
      "is_user_edited": false
    }
  ],
  "factions": [
    {
      "id": 1,
      "name": "Hunter's Association",
      "description": "...",
      "faction_type": "organization",
      "alignment": "protagonist",
      "members": [
        { "id": 3, "name": "Go Gun-hee", "member_role": "leader" }
      ]
    }
  ],
  "lore": [
    {
      "id": 1,
      "title": "The System",
      "content": "A mysterious game-like overlay that appears to chosen individuals...",
      "lore_type": "power_system",
      "first_appears_chapter_id": 1,
      "is_user_edited": false
    }
  ]
}
```

**Errors:** `series_not_found`.

---

### `POST /knowledge/world/locations`
### `PATCH /knowledge/world/locations/{id}`
### `DELETE /knowledge/world/locations/{id}`

CRUD for world locations. Same pattern as characters.

`POST` body: `{ series_id, name, description, location_type, parent_id }`.
`PATCH` sets `is_user_edited = true`.
`DELETE` sets children's `parent_id` to `null`.

---

### `POST /knowledge/world/factions`
### `PATCH /knowledge/world/factions/{id}`
### `DELETE /knowledge/world/factions/{id}`

CRUD for world factions. Same pattern.

`POST` body: `{ series_id, name, description, faction_type, alignment, parent_id }`.

---

### `POST /knowledge/world/lore`
### `PATCH /knowledge/world/lore/{id}`
### `DELETE /knowledge/world/lore/{id}`

CRUD for world lore entries.

`POST` body: `{ series_id, title, content, lore_type, first_appears_chapter_id }`.

---

### `POST /knowledge/series/{series_id}/world/extract`

Queue AI world extraction (locations, factions, lore, power systems).

**Response 202**
```json
{ "task_id": 106, "message": "World extraction queued." }
```

**Errors:** `series_not_found`, `ocr_not_complete`, `ollama_unavailable`.

---

## 20. Knowledge Graph: Scenes

### `GET /knowledge/series/{series_id}/scenes`

Story scenes for a series.

**Query parameters:** `chapter_id` (optional), `scene_type` (optional), `page`, `per_page`.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "series_id": 1,
      "chapter_id": 14,
      "page_start": 60,
      "page_end": 72,
      "scene_type": "plot_point",
      "title": "The System Awakening",
      "summary": "Jin-woo receives the system after surviving...",
      "significance": "critical",
      "location_id": null,
      "characters": [ { "id": 1, "name": "Sung Jin-woo" } ],
      "is_user_edited": false
    }
  ],
  "total": 1840
}
```

**Errors:** `series_not_found`.

---

### `POST /knowledge/scenes`
### `PATCH /knowledge/scenes/{id}`
### `DELETE /knowledge/scenes/{id}`

CRUD for story scenes.

`POST` body: `{ series_id, chapter_id, scene_type, title, summary, significance, page_start, page_end, character_ids, location_id }`.

---

### `POST /knowledge/series/{series_id}/scenes/generate`

Queue AI scene extraction.

**Response 202**
```json
{ "task_id": 107, "message": "Scene extraction queued." }
```

---

## 21. Background Tasks

### `GET /tasks`

All background tasks, optionally filtered.

**Query parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `status` | string | `pending` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `task_type` | string | `scan` \| `thumbnail` \| `ocr` \| `embed` \| `summarize` \| `knowledge` \| `download` |
| `subject_type` | string | `series` \| `chapter` \| `library` |
| `subject_id` | int | — |
| `page` | int | 1 |
| `per_page` | int | 20 |

**Response 200**
```json
{
  "items": [
    {
      "id": 42,
      "task_type": "ocr",
      "status": "running",
      "priority": 3,
      "subject_type": "series",
      "subject_id": 1,
      "progress_pct": 47.2,
      "progress_detail": "Page 6063 of 12853",
      "error_message": null,
      "retry_count": 0,
      "created_at": "2024-01-14T05:00:00Z",
      "started_at": "2024-01-14T05:00:01Z",
      "finished_at": null
    }
  ],
  "total": 12
}
```

---

### `GET /tasks/{id}`

Single task status.

**Response 200** — same shape as list item.

**Errors:** `task_not_found`.

---

### `POST /tasks/{id}/cancel`

Cancel a pending or running task.

**Response 200**
```json
{ "id": 42, "status": "cancelled" }
```

**Errors:** `task_not_found`, `task_not_cancellable`.

---

## 22. WebSocket Endpoints

### `WS /ws/tasks/{task_id}`

Stream real-time progress for a background task.

**Messages (server → client)**
```json
{ "task_id": 42, "status": "running", "progress_pct": 48.5, "progress_detail": "Page 6234 of 12853" }
{ "task_id": 42, "status": "completed", "progress_pct": 100.0, "finished_at": "2024-01-14T09:00:00Z" }
{ "task_id": 42, "status": "failed", "error_message": "Ollama stopped responding on page 8421" }
```

Connection closes automatically when the task reaches a terminal state
(`completed`, `failed`, or `cancelled`).

---

### `WS /ws/notifications`

Global notification stream. Delivers library change events in real time.

**Messages (server → client)**
```json
{ "type": "series_added",   "series_id": 248, "title": "Tower of God" }
{ "type": "series_updated", "series_id": 1,   "field": "total_chapters", "value": 180 }
{ "type": "scan_started",   "library_id": 1 }
{ "type": "scan_complete",  "library_id": 1, "added": 5, "updated": 12 }
{ "type": "task_queued",    "task_id": 43,   "task_type": "thumbnail" }
```

---

### `WS /ws/chat/{session_id}`

Alternative to SSE for chat streaming. Sends the same delta format as
`POST /ai/chat/sessions/{id}/messages` but over WebSocket.

**Messages (client → server)**
```json
{ "content": "Who is the Shadow Monarch?" }
```

**Messages (server → client)**
```json
{ "delta": "The Shadow " }
{ "delta": "Monarch is..." }
{ "done": true, "tokens_used": 312, "message_id": 49 }
```

---

## 23. Creation Studio Endpoints (Phase 5)

### `GET /create/projects`

All creation projects.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "title": "The Crimson Gate",
      "genre": "Action",
      "format": "manhwa",
      "status": "in_progress",
      "cover_url": null,
      "chapter_count": 3,
      "created_at": "2024-02-01T00:00:00Z"
    }
  ],
  "total": 2
}
```

---

### `POST /create/projects`

Create a new project.

**Request body**
```json
{
  "title": "The Crimson Gate",
  "genre": "Action",
  "format": "manhwa",
  "synopsis": "A hunter discovers a gate that changes everything.",
  "target_audience": "Young adult"
}
```

**Response 201** — full project object.

---

### `GET /create/projects/{id}`

Project detail with character roster and chapter list.

**Response 200**
```json
{
  "id": 1,
  "title": "The Crimson Gate",
  "genre": "Action",
  "format": "manhwa",
  "synopsis": "...",
  "target_audience": "Young adult",
  "status": "in_progress",
  "cover_url": null,
  "series_id": null,
  "character_count": 4,
  "chapter_count": 3,
  "created_at": "2024-02-01T00:00:00Z"
}
```

---

### `PATCH /create/projects/{id}` / `DELETE /create/projects/{id}`

Standard PATCH and DELETE. PATCH updates any project field.
DELETE removes project and all associated data.

---

### `POST /create/projects/{id}/export`

Export a project as a CBZ file and add it to the library.

**Request body**
```json
{
  "format": "cbz",
  "destination_library_id": 1
}
```

`format`: `cbz` | `pdf` | `folder`.

**Response 202**
```json
{ "task_id": 200, "message": "Export queued." }
```

---

### Character, Chapter, and Panel endpoints

`GET /create/projects/{id}/characters`
`POST /create/projects/{id}/characters`
`PATCH /create/characters/{id}`
`DELETE /create/characters/{id}`

`GET /create/projects/{id}/chapters`
`POST /create/projects/{id}/chapters`
`PATCH /create/chapters/{id}`
`DELETE /create/chapters/{id}`

`GET /create/chapters/{id}/panels`
`POST /create/chapters/{id}/panels`
`PATCH /create/panels/{id}`
`DELETE /create/panels/{id}`

All follow the same CRUD pattern. See the database schema for field lists.

---

### `POST /create/generate/image`

Generate an image via ComfyUI.

**Request body**
```json
{
  "project_id": 1,
  "panel_id": 42,
  "prompt": "A young hunter standing before a glowing crimson gate, dramatic lighting",
  "negative_prompt": "blurry, low quality",
  "workflow_id": 1,
  "width": 768,
  "height": 1152,
  "seed": null
}
```

`seed` is optional. `null` = random.

**Response 202**
```json
{ "task_id": 201, "message": "Image generation queued." }
```

**Errors:** `not_found`, `comfyui_unavailable`.

---

### `GET /create/assets/{project_id}`

All generated assets for a project.

**Query parameters:** `character_id` (optional), `panel_id` (optional), `asset_type` (optional).

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "asset_type": "panel",
      "image_url": "/create/assets/1/image",
      "prompt": "...",
      "model": "dreamshaper_xl",
      "seed": 42389174,
      "width": 768,
      "height": 1152,
      "created_at": "2024-02-01T10:00:00Z"
    }
  ],
  "total": 87
}
```

---

### `GET /create/assets/{id}/image`

Serve a generated asset image.

**Response 200** — binary image data.

---

### Workflow endpoints

`GET /create/workflows` — list saved ComfyUI workflows.
`POST /create/workflows` — save a workflow JSON.
`PATCH /create/workflows/{id}` — update a workflow.
`DELETE /create/workflows/{id}` — delete a workflow.

---

## 24. Downloads Endpoints (Phase 6)

### `GET /downloads/sources`

All configured download sources.

**Response 200** — list of source objects `{ id, name, source_type, base_url, is_active }`.

---

### `POST /downloads/sources`

Add a download source.

**Request body**
```json
{
  "name": "MangaDex",
  "source_type": "mangadex",
  "base_url": "https://api.mangadex.org",
  "config": { "rate_limit_per_second": 2 }
}
```

**Response 201** — full source object.

---

### `GET /downloads/jobs`

Download queue.

**Query parameters:** `status`, `source_id`, `series_id`, `page`, `per_page`.

**Response 200**
```json
{
  "items": [
    {
      "id": 1,
      "source_id": 1,
      "series_id": null,
      "url": "https://api.mangadex.org/...",
      "job_type": "chapter",
      "status": "downloading",
      "display_title": "Tower of God — Chapter 600",
      "expected_bytes": 15728640,
      "downloaded_bytes": 7340032,
      "error_message": null,
      "retry_count": 0,
      "created_at": "2024-06-01T10:00:00Z",
      "started_at": "2024-06-01T10:00:01Z"
    }
  ],
  "total": 42
}
```

---

### `POST /downloads/jobs`

Queue a download.

**Request body**
```json
{
  "source_id": 1,
  "url": "https://...",
  "job_type": "chapter",
  "display_title": "Tower of God — Chapter 600",
  "destination_library_id": 1
}
```

**Response 202** — full job object with `status: "pending"`.

---

### `POST /downloads/jobs/{id}/pause`
### `POST /downloads/jobs/{id}/resume`
### `POST /downloads/jobs/{id}/cancel`
### `POST /downloads/jobs/{id}/retry`

Job lifecycle actions. Each returns the updated job object on `200`.

**Errors:** `task_not_found`, `task_not_cancellable` (for cancel/pause on completed jobs).

---

## 25. Endpoint Index

| Method | Path | Phase | Purpose |
|--------|------|-------|---------|
| GET | `/` | 1 | Service status |
| GET | `/health` | 2 | Component health |
| GET | `/settings` | 2 | User preferences |
| PATCH | `/settings` | 2 | Update preferences |
| GET | `/library/roots` | 2 | List library roots |
| POST | `/library/roots` | 2 | Register library root |
| DELETE | `/library/roots/{id}` | 2 | Remove library root |
| POST | `/library/roots/{id}/scan` | 2 | Trigger rescan |
| GET | `/library/series` | 2 | Paginated series list |
| GET | `/library/series/{id}` | 2 | Series detail |
| PATCH | `/library/series/{id}` | 2 | Edit series metadata |
| DELETE | `/library/series/{id}` | 2 | Soft-delete series |
| GET | `/library/series/{id}/chapters` | 2 | Chapter list |
| GET | `/library/series/{id}/volumes` | 2 | Volume list |
| GET | `/library/series/{id}/ai-status` | 3 | AI pipeline progress |
| POST | `/library/import` | 2 | Start background import |
| GET | `/library/covers/series/{id}` | 2 | Series cover image |
| GET | `/library/covers/chapter/{id}` | 2 | Chapter cover image |
| GET | `/library/chapters/{id}` | 2 | Chapter + pages |
| POST | `/library/chapters/{id}/mark-read` | 2 | Mark chapter read |
| GET | `/library/collections` | 2 | All collections |
| POST | `/library/collections` | 2 | Create collection |
| GET | `/library/collections/{id}` | 2 | Collection + series |
| PATCH | `/library/collections/{id}` | 2 | Edit collection |
| DELETE | `/library/collections/{id}` | 2 | Delete collection |
| POST | `/library/collections/{id}/series/{sid}` | 2 | Add to collection |
| DELETE | `/library/collections/{id}/series/{sid}` | 2 | Remove from collection |
| GET | `/library/tags` | 2 | All tags |
| POST | `/library/tags` | 2 | Create tag |
| DELETE | `/library/tags/{id}` | 2 | Delete tag |
| POST | `/library/series/{id}/tags` | 2 | Tag a series |
| DELETE | `/library/series/{id}/tags/{tag_id}` | 2 | Untag a series |
| GET | `/reader/chapters/{id}` | 2 | Chapter for reader |
| GET | `/reader/pages/{id}/image` | 2 | Page image (hot path) |
| GET | `/reader/series/{id}/progress` | 2 | Resume position |
| POST | `/reader/progress` | 2 | Save progress |
| GET | `/reader/series/{id}/next-chapter` | 2 | Next unread chapter |
| GET | `/reader/series/{id}/bookmarks` | 2 | All bookmarks |
| POST | `/reader/bookmarks` | 2 | Create bookmark |
| DELETE | `/reader/bookmarks/{id}` | 2 | Delete bookmark |
| GET | `/search` | 2 | Unified search |
| GET | `/search/series` | 2 | Series-only FTS |
| GET | `/search/ocr` | 3 | Dialogue search |
| GET | `/search/semantic` | 3 | Semantic vector search |
| POST | `/ai/analyze/{series_id}` | 3 | Queue full AI pipeline |
| GET | `/ai/analyze/{series_id}/status` | 3 | Pipeline status |
| POST | `/ai/ocr/chapter/{id}` | 3 | Queue chapter OCR |
| GET | `/ai/ocr/chapter/{id}/status` | 3 | OCR status |
| GET | `/ai/ocr/page/{id}` | 3 | Page OCR text |
| GET | `/ai/summaries/series/{id}` | 3 | All series summaries |
| GET | `/ai/summaries/chapter/{id}` | 3 | Chapter summary |
| PUT | `/ai/summaries/{id}` | 3 | Edit summary |
| POST | `/ai/summaries/series/{id}/generate` | 3 | Regenerate summaries |
| POST | `/ai/metadata/series/{id}/extract` | 3 | Extract metadata |
| GET | `/ai/chat/series/{id}/sessions` | 3 | Chat sessions |
| POST | `/ai/chat/sessions` | 3 | Create session |
| POST | `/ai/chat/sessions/{id}/messages` | 3 | Send message (SSE) |
| GET | `/ai/chat/sessions/{id}/messages` | 3 | Message history |
| DELETE | `/ai/chat/sessions/{id}` | 3 | Delete session |
| GET | `/knowledge/series/{id}/characters` | 4 | Characters |
| POST | `/knowledge/characters` | 4 | Create character |
| GET | `/knowledge/characters/{id}` | 4 | Character detail |
| PATCH | `/knowledge/characters/{id}` | 4 | Edit character |
| DELETE | `/knowledge/characters/{id}` | 4 | Delete character |
| GET | `/knowledge/characters/{id}/appearances` | 4 | Appearances |
| GET | `/knowledge/series/{id}/relationships` | 4 | Relationship graph |
| POST | `/knowledge/relationships` | 4 | Create relationship |
| PATCH | `/knowledge/relationships/{id}` | 4 | Edit relationship |
| DELETE | `/knowledge/relationships/{id}` | 4 | Delete relationship |
| GET | `/knowledge/series/{id}/timeline` | 4 | Timeline |
| POST | `/knowledge/series/{id}/timeline/generate` | 4 | Generate timeline |
| POST | `/knowledge/timeline/events` | 4 | Create event |
| PATCH | `/knowledge/timeline/events/{id}` | 4 | Edit event |
| DELETE | `/knowledge/timeline/events/{id}` | 4 | Delete event |
| GET | `/knowledge/series/{id}/world` | 4 | World data |
| POST | `/knowledge/world/locations` | 4 | Create location |
| PATCH | `/knowledge/world/locations/{id}` | 4 | Edit location |
| DELETE | `/knowledge/world/locations/{id}` | 4 | Delete location |
| POST | `/knowledge/world/factions` | 4 | Create faction |
| PATCH | `/knowledge/world/factions/{id}` | 4 | Edit faction |
| DELETE | `/knowledge/world/factions/{id}` | 4 | Delete faction |
| POST | `/knowledge/world/lore` | 4 | Create lore entry |
| PATCH | `/knowledge/world/lore/{id}` | 4 | Edit lore |
| DELETE | `/knowledge/world/lore/{id}` | 4 | Delete lore |
| POST | `/knowledge/series/{id}/world/extract` | 4 | Extract world data |
| GET | `/knowledge/series/{id}/scenes` | 4 | Story scenes |
| POST | `/knowledge/scenes` | 4 | Create scene |
| PATCH | `/knowledge/scenes/{id}` | 4 | Edit scene |
| DELETE | `/knowledge/scenes/{id}` | 4 | Delete scene |
| POST | `/knowledge/series/{id}/scenes/generate` | 4 | Generate scenes |
| GET | `/tasks` | 2 | Task queue |
| GET | `/tasks/{id}` | 2 | Task status |
| POST | `/tasks/{id}/cancel` | 2 | Cancel task |
| WS | `/ws/tasks/{id}` | 2 | Task progress stream |
| WS | `/ws/notifications` | 2 | Library change events |
| WS | `/ws/chat/{session_id}` | 3 | Chat streaming |
| GET | `/create/projects` | 5 | Projects |
| POST | `/create/projects` | 5 | Create project |
| GET | `/create/projects/{id}` | 5 | Project detail |
| PATCH | `/create/projects/{id}` | 5 | Edit project |
| DELETE | `/create/projects/{id}` | 5 | Delete project |
| POST | `/create/projects/{id}/export` | 5 | Export to library |
| GET | `/create/projects/{id}/characters` | 5 | Project characters |
| POST | `/create/projects/{id}/characters` | 5 | Create character |
| PATCH | `/create/characters/{id}` | 5 | Edit character |
| DELETE | `/create/characters/{id}` | 5 | Delete character |
| GET | `/create/projects/{id}/chapters` | 5 | Project chapters |
| POST | `/create/projects/{id}/chapters` | 5 | Create chapter |
| PATCH | `/create/chapters/{id}` | 5 | Edit chapter |
| DELETE | `/create/chapters/{id}` | 5 | Delete chapter |
| GET | `/create/chapters/{id}/panels` | 5 | Panels |
| POST | `/create/chapters/{id}/panels` | 5 | Create panel |
| PATCH | `/create/panels/{id}` | 5 | Edit panel |
| DELETE | `/create/panels/{id}` | 5 | Delete panel |
| POST | `/create/generate/image` | 5 | Generate image |
| GET | `/create/assets/{project_id}` | 5 | Asset library |
| GET | `/create/assets/{id}/image` | 5 | Serve asset |
| GET | `/create/workflows` | 5 | ComfyUI workflows |
| POST | `/create/workflows` | 5 | Save workflow |
| PATCH | `/create/workflows/{id}` | 5 | Edit workflow |
| DELETE | `/create/workflows/{id}` | 5 | Delete workflow |
| GET | `/downloads/sources` | 6 | Download sources |
| POST | `/downloads/sources` | 6 | Add source |
| PATCH | `/downloads/sources/{id}` | 6 | Edit source |
| DELETE | `/downloads/sources/{id}` | 6 | Remove source |
| GET | `/downloads/jobs` | 6 | Download queue |
| POST | `/downloads/jobs` | 6 | Queue download |
| GET | `/downloads/jobs/{id}` | 6 | Job status |
| POST | `/downloads/jobs/{id}/pause` | 6 | Pause |
| POST | `/downloads/jobs/{id}/resume` | 6 | Resume |
| POST | `/downloads/jobs/{id}/cancel` | 6 | Cancel |
| POST | `/downloads/jobs/{id}/retry` | 6 | Retry |
| DELETE | `/downloads/jobs/{id}` | 6 | Delete job |
