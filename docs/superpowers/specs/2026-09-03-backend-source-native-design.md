# Backend: source-native rebuild (VPS slim-down, client-side downloads)

**Date:** 2026-09-03
**Status:** Design — approved for spec, not yet planned
**Sub-project:** 1 of 3 (backend). Follow-ups: 1b web client, 1c mobile client.
**Supersedes for the download path:** `docs/OFFLINE_READING.md` (which assumed
NAS-primary + phone-mirror; this flips to phone-only).

---

## 1. Why

The product runs two parallel worlds:

1. **Catalog / Library** — `libraries` / `series` / `chapters` / `pages`,
   populated by a disk scanner and a server-side download engine
   (`DownloadManager`) that scrapes chapters and writes page images to an
   unbounded `/downloads` volume. The reader serves those bytes from disk.
2. **Sources** — live connectors that scrape upstream sites. Online reading
   proxies each image on demand (`GET /sources/{id}/pages/{id}/image`); nothing
   is stored.

World 1 cannot run on the target host: a **VPS with ≤20 GB of disk**. Chapter
images are the only thing that grows without bound and they must not live on the
server.

**Decision:** delete world 1 entirely. The backend becomes a connector +
image-proxy + metadata store. All chapter bytes live on the client (phone or
browser), downloaded through the existing source image-proxy. This spec covers
the **backend** only.

### Ratified constraints (from brainstorming, 2026-09-03)

| Constraint | Value |
|---|---|
| Existing server/NAS library | **Deleted.** No read-only retention, no migration of content. |
| Database | **Wiped.** Fresh Alembic baseline; no data migration from the old schema. |
| Multi-user | **Kept and finished.** Multiple accounts, each with multiple profiles; per-profile data isolation. |
| Web client | **Full parity** with mobile (offline downloads included — sub-project 1b). |
| iOS distribution | Free sideload (SideStore). Shapes 1c, not this spec. |
| OCR dialogue search | **Kept, client-driven.** Phone runs OCR on downloaded pages; uploads text to the server. |
| Data model | **Source-native** (approach A): everything keys on `(source_id, series_key, chapter_key)` strings. Catalog tables deleted. |

---

## 2. Identity model

- **Series** = `(source_id: str, series_key: str)`
- **Chapter** = `(source_id, series_key, chapter_key: str)`
- `series_key` / `chapter_key` are **opaque connector strings**. They may contain
  slashes and percent-encoding (connectors already route them as `:path`
  params). Store them **raw and exact**. Never parse, split, or normalise beyond
  the existing `connectors.ids.fully_unquote` at the HTTP boundary.
- `chapter_number: float | None` is carried on every progress/notification/cache
  row. It is the **only stable axis across sources** (keys are per-source, titles
  are translations) and is what a future "this source died, follow it on another"
  migration maps progress by. Keep `known_chapters` as
  `[{key, number, title, published_at}]`.

---

## 3. Target schema (fresh Alembic baseline)

The database is wiped. `alembic/versions/*` is deleted and replaced with a
single baseline revision `0001_source_native`. `init_db()` loses the legacy
`_migrate_intelligence_columns` / `_migrate_chapter_number_to_float` /
`_schema_matches_head` / `_ensure_auth_tables` adoption machinery — there is no
pre-Alembic database to adopt any more.

### 3.1 Kept unchanged

`users`, `sessions`, `reading_profiles`, `source_pins`, `source_health`,
`update_settings`, `update_runs`.

> `update_settings.auto_download_enabled` column is **dropped** (see §5.4).

### 3.2 `followed_series` — the library

Replaces `series_trackers` + `user_series_state` + `libraries`. **A series is in
a profile's library iff a `followed_series` row exists for it.** No `track_kind`
(there is no "downloaded" state the server knows about).

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | FK `users.id`, **NOT NULL** | fresh DB → no legacy NULLs |
| `profile_id` | FK `reading_profiles.id` ON DELETE CASCADE, **NOT NULL** | per-profile isolation |
| `source_id` | str(64) NOT NULL | connector key |
| `series_key` | str(512) NOT NULL | opaque |
| `title` | str(512) NOT NULL | snapshot for offline library display |
| `cover_url` | str(1024) \| NULL | snapshot (upstream URL, proxied on render) |
| `is_favorite` | bool default 0 | |
| `reading_status` | str(32) default `'reading'` | unread/reading/completed/on_hold/dropped/plan_to_read |
| `notify` | bool default 1 | new-chapter notifications |
| `sort_order` | int default 0 | manual ordering; default list order is `title` |
| `content_rating` | str(32) \| NULL | captured at follow from connector genres; NULL = "no signal" → resolves to `unknown` |
| `mature_override` | bool \| NULL | user's explicit verdict; wins over everything (`core.content_rating.resolve_*`) |
| `known_chapters` | Text (JSON) NOT NULL default `'[]'` | `[{key, number, title, published_at}]` snapshot from last update check |
| `last_checked_at` | datetime \| NULL | |
| `last_error` | Text \| NULL | |
| `migrated_from_source` / `migrated_from_series_key` / `migrated_at` | audit trail for a source repoint |
| `created_at` / `updated_at` | datetime | |

**Constraints / indexes:**
- `UNIQUE (user_id, profile_id, source_id, series_key)`
- `INDEX (user_id, profile_id, sort_order)` — the library grid read
- `INDEX (source_id)` — the update scheduler's per-source sweep
- `INDEX (user_id, profile_id, is_favorite)`
- `INDEX (content_rating)` — the 18+ gate filters every library read

### 3.3 `chapter_progress` — reading position

Merges `reading_progress` + `chapter_progress` into one source-native table.
Per-profile. "Continue reading" is the most recent row per `(source, series_key)`.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `user_id` | FK `users.id`, NOT NULL | |
| `profile_id` | FK `reading_profiles.id` ON DELETE CASCADE, NOT NULL | |
| `source_id` / `series_key` / `chapter_key` | str | |
| `chapter_number` | float \| NULL | stable axis |
| `last_page` | int default 1 | |
| `page_count` | int default 0 | snapshot at read time; lets "12/27" render offline |
| `scroll_offset_px` | int default 0 | webtoon vertical position |
| `is_completed` | bool default 0 | sticky |
| `started_at` / `last_read_at` / `completed_at` | datetime | |
| `time_spent_seconds` | int default 0 | |

**Constraints / indexes:**
- `UNIQUE (user_id, profile_id, source_id, series_key, chapter_key)`
- `INDEX (user_id, profile_id, last_read_at)` — continue-reading strip
- `INDEX (user_id, profile_id, source_id, series_key)` — per-series chapter states

**Merge rule for sync (client pushes progress):** **furthest-wins** on
`(chapter_number, last_page)`, `last_read_at` as tie-break only, `is_completed`
sticky. Never last-write-wins (silently rewinds the reader). This matches
`docs/OFFLINE_READING.md` §3.

### 3.4 `bookmarks`

Source-native rekey of the existing table. `user_id` / `profile_id` NOT NULL.
Columns: `source_id`, `series_key`, `chapter_key`, `page` int, `note` Text|NULL,
`created_at`. Drops the `page_id` FK (no `pages` table).

### 3.5 `reading_sessions`

Source-native rekey (history + statistics). `user_id` / `profile_id` NOT NULL.
Columns: `source_id`, `series_key`, `chapter_key`, `chapter_number`,
`start_page`, `end_page`, `pages_read`, `started_at`, `ended_at`.
Indexes: `(user_id, profile_id, started_at)`.

### 3.6 `collections` / `collection_series`

- `collections`: shape unchanged (`user_id`/`profile_id` NOT NULL, `name`,
  `description`, `cover_url` renamed from `cover_path`, `sort_order`).
  `UNIQUE (user_id, profile_id, name)`.
- `collection_series`: PK becomes `(collection_id, source_id, series_key)`.
  Columns: `sort_order`, `added_at`.

### 3.7 `tags` / `profile_series_tags`

- `tags`: global label vocabulary — `id`, `name` UNIQUE, `category`, `color`.
  (Kept global: a tag is a word, not owned data. Open question O-3.)
- `profile_series_tags` (replaces `series_tags`): `user_id`, `profile_id`,
  `source_id`, `series_key`, `tag_id`, `is_ai_generated`, `confidence`.
  PK `(user_id, profile_id, source_id, series_key, tag_id)`.

### 3.8 `update_notifications`

Source-native rekey. `user_id`/`profile_id` NOT NULL (denormalised from the
tracker for join-free scoped lists). FK `followed_series_id` → `followed_series.id`
ON DELETE CASCADE. Columns: `source_id`, `series_key`, `chapter_key`,
`chapter_title`, `chapter_number`, `is_read`, `created_at`.

### 3.9 `chapter_ocr` — dialogue text (GLOBAL)

Merges `ocr_jobs` + `page_texts` + `chapter_texts` into **one row per chapter**,
**not per user**. Rationale mirrors `source_health`: the OCR text of a chapter is
a property of the chapter. Any profile that has downloaded that chapter and run
OCR contributes; any profile searching benefits. No disclosure risk — search
results are still filtered through the caller's followed-series + 18+ gate before
return.

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `source_id` / `series_key` / `chapter_key` | str | |
| `full_text` | Text \| NULL | aggregated, for FTS |
| `page_texts` | Text (JSON) \| NULL | `[{page, text, boxes}]` for in-reader highlight |
| `language` | str(16) \| NULL | |
| `engine` | str(64) | e.g. `tesseract`, `apple-vision`, `mlkit` |
| `word_count` | int default 0 | |
| `contributed_by_user_id` | int \| NULL | audit only, not a scope |
| `created_at` / `updated_at` | datetime | |

`UNIQUE (source_id, series_key, chapter_key)`. An upload for an existing key
**replaces** (last engine wins) unless the incoming `word_count` is 0.

No `OcrJob` queue table — job state is entirely client-side now.

### 3.10 `source_series_cache` — connector metadata cache (GLOBAL, NEW)

A TTL cache so the library grid, continue-reading strip, and notifications can
render titles/covers/chapter counts without hitting a connector every time.
**Purely a cache** — any row may be deleted at any time and is repopulated on the
next browse/read.

| Column | Type | Notes |
|---|---|---|
| `source_id` / `series_key` | str, composite PK | |
| `title` | str(512) | |
| `cover_url` | str(1024) \| NULL | |
| `description` | Text \| NULL | |
| `author` / `artist` | str(255) \| NULL | |
| `status` | str(64) \| NULL | ongoing/completed/hiatus |
| `year` | int \| NULL | |
| `content_rating` | str(32) \| NULL | |
| `genres` | Text (JSON) \| NULL | |
| `chapters` | Text (JSON) \| NULL | `[{key, number, title, published_at, page_count?}]` |
| `fetched_at` | datetime | TTL check (default 6 h, config `MM_SOURCE_CACHE_TTL_MINUTES`) |

Writes happen opportunistically whenever `browse_service` / `source_service`
fetches fresh connector data. Reads fall back to a live connector fetch on miss
or stale.

### 3.11 Deleted tables

`libraries`, `series`, `chapters`, `volumes`, `pages`, `downloads`,
`download_queue`, `source_chapter_links`, `import_history`, `series_trackers`,
`user_series_state`, `ocr_jobs`, `page_texts`, `chapter_texts`,
`reading_progress`, and the `series_fts` virtual table + its triggers.

### 3.12 FTS5

- **Drop** `series_fts` (there is no `series` table). Library search is a SQL
  `LIKE` / `IN` over the small per-profile `followed_series.title` set — no FTS
  needed.
- **Add** `chapter_ocr_fts` over `chapter_ocr.full_text` (external-content FTS5,
  `content='chapter_ocr'`, `content_rowid='id'`, same trigger pattern as the old
  `series_fts`). Powers dialogue search.

---

## 4. New / changed endpoints

### 4.1 Reader

| Method | Path | Change |
|---|---|---|
| `GET` | `/reader/chapter/manifest?source=&series=&chapter=` | **NEW.** The download plan: `{ page_count, chapter_number, pages: [{number, url, sha256?, size?}], prev, next }`. No bytes. `url` points at the existing proxy. `sha256`/`size` are best-effort from the connector; absent is fine. |
| `GET` | `/sources/{source_id}/pages/{page_id:path}/image` | **Unchanged** — stays the byte source for both online reading and client downloads. **No server-side cache added.** |
| `GET` | `/reader/chapter/{id}` (int) | **Deleted** (no local chapters). |
| `GET` | `/reader/page/{page_id}/image` (int) | **Deleted.** |
| `POST` | `/reader/progress` | Body becomes `{ source_id, series_key, chapter_key, chapter_number, last_page, page_count, scroll_offset_px, is_completed }`. Applies the furthest-wins merge. `require_profile_context`. |
| `POST` | `/reader/progress/batch` | **NEW.** Array of the above for offline sync catch-up. |
| `POST` | `/reader/bookmark` | Source-native body. |

### 4.2 Library (`/library`)

`routes/library.py` is rewritten around `followed_series`. `/import`,
`/scan-status`, `/libraries`, `/pages/{id}/image`, `/chapters/{id}` are
**deleted**. Kept/rewritten: `/series` (list followed, filter/sort/paginate),
`GET /series/{followed_id}` (detail = cache + live chapter list),
`POST /follow` `{source_id, series_key}` (replaces `/series/{id}/add`),
`DELETE /follow/{followed_id}`, `PATCH /series/{followed_id}` (favorite, status,
notify), `/continue-reading`, `/reading-history`, `/recently-updated`,
`/statistics`, `/collections/*`, `/tags/*`, `/recommendations`, `/search`
(over followed set).

### 4.3 Downloads (`/downloads`)

**Router deleted entirely.** No server-side download concept.

### 4.4 OCR (`/ocr`)

Rewritten to ingest + search only:

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ocr/chapter` | Client uploads `{source_id, series_key, chapter_key, chapter_number, language, engine, pages: [{page, text, boxes}]}`. Upserts `chapter_ocr`, rebuilds `full_text`. |
| `GET` | `/ocr/chapter?source=&series=&chapter=` | Returns stored `page_texts` for in-reader highlighting (if present). |
| `GET` | `/ocr/search?q=` | FTS over `chapter_ocr_fts`, results filtered to the caller's followed series + 18+ gate. |
| `GET` | `/ocr/coverage?source=&series=` | Which chapters already have OCR (so the client only OCRs the gaps). |

`OcrManager`, `ocr_pipeline.py`, `ocr_engine.py`, `ocr_utils.py` (the
tesseract/easyocr runner) are **deleted**. `ocr_search.py` is kept/rewritten
against `chapter_ocr`.

### 4.5 Updates (`/updates`)

Kept. `update_scheduler.py` / `update_service.py` rewritten to diff each
`followed_series.known_chapters` against a live connector chapter list, write
`update_notifications`, and refresh `source_series_cache`. `auto_download_*` is
removed (`update_auto_download.py` deleted, the `register_new_chapters_callback`
hook in `main.py` removed). New chapters produce a **notification only**; the
client decides whether to download.

### 4.6 Backup (`/backup`)

Kept, admin-only. Now backs up only the metadata DB (already the case —
`/downloads` was never in the backup). No functional change beyond the smaller
schema.

---

## 5. Service layer

### 5.1 Deleted service files

`download_manager.py`, `download_service.py`, `download_scheduling.py`,
`download_support.py`, `nas_listing.py`, `import_cleanup.py`,
`update_auto_download.py`, `ocr_pipeline.py`, `ocr_engine.py`, `ocr_utils.py`,
`image_service.py`, `library_intelligence_service.py` (folds into the new
followed-series service).

### 5.2 New / rewritten

| File | Role |
|---|---|
| `followed_series_service.py` | CRUD + list/filter/sort/paginate over `followed_series`; 18+ gate; content-rating resolution; collections; tags; statistics; recommendations (still "similar by genre" over the followed set — no external AI yet). |
| `reader_service.py` | `manifest()` (connector → page list), `resolve_source_chapter()` (unchanged online path, minus the "local copy shortcut" branch). |
| `progress_service.py` | furthest-wins merge, batch apply, continue-reading, history. |
| `ocr_ingest_service.py` | upsert `chapter_ocr`, rebuild `full_text`, coverage. |
| `ocr_search.py` | FTS query + caller-scope filter. |
| `update_service.py` / `update_scheduler.py` | connector-diff sweep, notifications, cache refresh. Single-process loop (unchanged threading model). |
| `source_cache_service.py` | read-through TTL cache wrapping `browse_service` / `source_service`. |

### 5.3 Authorization

`core/library_authz.py` (`series_read_allowed`) is **deleted**. There is no
local content to guess-fetch by numeric id; every content read now goes through
a connector with the caller's own request context, and every metadata read is a
scoped query on `followed_series` / `chapter_progress` keyed by
`(user_id, profile_id)`.

**Isolation level: per-profile.** Unlike the old household-shared catalog, each
profile has its own follows, progress, collections, bookmarks, and
notifications. Cross-profile visibility is none by default. `require_profile_context`
guards every mutating route; `resolve_profile_context` (lenient) builds the
per-request services for reads.

`auth_service.py`: `_claim_unowned_data` / bootstrap "claim NULL-owned rows"
logic is **removed** — a wiped DB has no unowned rows, and every new table is
`user_id`/`profile_id` NOT NULL. First-registered-user-is-admin stays.

### 5.4 `main.py` lifespan

```
- get_download_manager().start()      # REMOVED
- get_ocr_manager().start()           # REMOVED
- get_update_manager().start()        # KEPT (single-process notify sweep)
- register_new_chapters_callback(auto_download_new_chapters)  # REMOVED
- run_startup_migrations() -> ImportCleanupService(...).merge_all_orphans_global()  # REMOVED
```

`run_startup_migrations()` collapses to `init_db()` + `prune_expired_sessions()`.

---

## 6. Config / infra

`backend/core/config.py` — remove: `downloads_path`, `import_roots`, all
`download_*` concurrency/retry settings, OCR engine settings. Add:
`source_cache_ttl_minutes` (default 360).

`docker-compose.yml` — remove: the `${MM_DOWNLOADS_HOST_DIR}:/downloads` bind
mount, `MM_DOWNLOADS_PATH`, `MM_IMPORT_ROOTS` env. Keep: `data` volume (DB +
settings), the `apk`/`ipa`/`pubspec`/`screenshots` mounts (sub-project 3 uses
them), the `edge` network.

`docs/AUTH.md` — the import-containment section is deleted (no import). Rate-limit
`import` bucket removed; `sources` bucket stays.

Result: backend container disk = image + code + `data` volume (SQLite, KB–MB
range). Well under 20 GB with room for everything else on the box.

---

## 7. Tests

- **Delete:** every test under `backend/tests/` exercising downloads, the disk
  scanner, `/library/import`, `image_service`, the OCR runner, catalog models.
- **Rewrite:** `test_reader_*`, `test_library_*`, `test_updates_*`, `test_ocr_*`,
  `test_progress_*`, `test_auth_enforcement` (per-profile scope), `conftest.py`
  fixtures (no catalog seed; seed `followed_series` + `chapter_progress`).
- **New:**
  - furthest-wins merge unit tests (rewind attempts, tie-breaks, sticky
    completion, batch)
  - per-profile isolation: profile A's follows/progress/notifications invisible
    to profile B (same account) and to another account
  - `chapter_ocr` global-write + scoped-search (B can't see A's OCR result for a
    series B doesn't follow)
  - `source_series_cache` TTL: hit, stale refetch, connector-down serves stale
  - `/reader/chapter/manifest` shape against a fixture connector
  - Alembic baseline: `upgrade head` on an empty DB creates every table; FTS5
    triggers fire.
- **Keep:** connector contract tests, SSRF tests, auth primitive tests, rate-limit
  tests.

---

## 8. Rollout

1. Land this on `feat/vps-slim-source-native`.
2. On the VPS: deploy with a **fresh empty `data` volume** (or `rm` the existing
   `manhwamaniacs.db`). Alembic baseline builds the schema on first boot.
3. First registered account = admin. Each person registers, creates profiles,
   re-follows their series.
4. 1b (web) and 1c (mobile) follow on the **same branch**. The branch is not
   merged to `main` or deployed to a shared instance until all three land.
   Between 1a and 1b/1c the clients do not work against the new API — acceptable
   because nothing is deployed yet.

> **Sequencing note:** because 1b/1c are separate specs but the clients cannot
> talk to the new backend until they are updated, the branch `feat/vps-slim-source-native`
> is **not merged to `main`** until all three land. Each sub-project is its own
> spec + plan + review, all on the one branch.

---

## 9. Open questions (resolve during planning, not blockers)

- **O-1 — `manifest` page hashes.** Connectors don't currently expose per-page
  `sha256`/`size` without fetching the bytes. v1: omit them; the client
  content-addresses by hashing what it downloads. Revisit if dedupe needs
  server-provided hashes.
- **O-2 — cover proxying.** `followed_series.cover_url` is an upstream URL.
  Render path proxies it via `/sources/{id}/series/{key}/cover` (exists). Confirm
  that route doesn't assume a catalog row.
- **O-3 — tags global vs per-user.** Spec says global vocabulary + per-profile
  assignment. If that feels wrong in practice, make the whole `tags` table
  per-user. Low stakes.
- **O-4 — `reading_status` / `is_favorite` on `followed_series` vs a separate
  state table.** Folded into `followed_series` here (one row per follow). The old
  split (`user_series_state` with `in_library=False` rows) existed to keep
  progress after un-following; in the new model progress lives in its own table
  keyed by `(source, series_key)` and survives an unfollow regardless. Confirm no
  flow needs a "state without follow" row.
- **O-5 — `known_chapters` size.** Long-running series (1000+ chapters) make this
  JSON blob large on every `followed_series` row. If it bites, move to a
  `followed_series_chapter` child table. Measure first.
- **O-6 — profile deletion.** `ON DELETE CASCADE` from `reading_profiles` wipes
  that profile's follows/progress/collections/notifications. Confirm that's the
  desired behaviour (vs. reassign-to-another-profile).
