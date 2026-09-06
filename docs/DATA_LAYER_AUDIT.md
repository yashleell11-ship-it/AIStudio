# Data-layer audit

Run 2026-09-06 across the whole persistence layer: the server SQLite database, the
phone's on-device store and outboxes, and the website's browser storage. Sixteen
read-only shards, each asked to prove what it found with a failing test rather than
assert it. They produced **132 findings**; the table below is all of them.

Severity is the finder's, adjusted where a verification round disagreed. Status:

- **shipped** — fixed and deployed already
- **fixed** — fixed, tested, and going out in 2.7.0
- **partial** — the reported harm is closed; a named remainder is not
- **by design** — real, and the owner has decided to keep it
- **open** — real as far as the evidence goes, not yet scheduled
- **unproven** — a hypothesis the shard could not confirm; treat as a lead, not a bug

The reproduction tests live beside the code they exercise, named `*audit*`.


## Users, sessions and the bootstrap claim

| id | sev | status | finding |
|---|---|---|---|
| `A-1` | critical | by design | Registration is open to the internet with no invite code. Confirmed deliberate on 2026-09-06: the owner wants anyone who finds the site to sign up. `is_admin` is only ever granted to the first-ever registration, so an open signup is an ordinary user. Do not re-raise. |
| `A-2` | high | fixed | Bootstrap window (0003) does not bound the admin claim when registration is open — expired window + empty users table still mints an owner |
| `A-3` | medium | fixed | No per-user session cap: every login inserts a 7/90-day row and nothing trims them |
| `A-7` | medium | fixed | No way to disable, kick, or delete an account: users.is_active has no writer and there is no user-delete path |
| `A-4` | low | fixed | Expired sessions are only swept at process startup or when the dead token itself is presented |
| `A-5` | low | fixed | sessions.ip_address records the first X-Forwarded-For hop: client-forgeable, and on the VPS it is always the cloudflared container |
| `A-6` | low | fixed | Password change and other-session revocation are two separate commits |
| `A-8` | low | fixed | Redundant indexes: ix_sessions_token_hash duplicates the UNIQUE autoindex on token_hash; ix_users_username duplicates uq_users_username |
| `A-9` | low | unproven | Hypothesis: login rate limit may be keyed on a single shared IP if CF-Connecting-IP does not reach the backend |

## Durability and operations

| id | sev | status | finding |
|---|---|---|---|
| `BK-1` | high | shipped | No scheduled backup of the SQLite database anywhere; only copies are manual admin exports |
| `BK-2` | high | fixed | Restore-on-boot overwrites the live database and keeps no copy of it |
| `BK-5` | high | shipped | Root disk at 80%: 18.6 GB of it is unreferenced Docker build cache, growing ~2 GB per push |
| `BK-3` | medium | fixed | Backup import validation accepts a corrupt database (only sqlite_master is read) |
| `BK-4` | medium | fixed | Restoring a backup taken from a newer build crash-loops the backend with the old DB already gone |
| `BK-6` | low | open | WAL only checkpoints on restart and PRAGMA optimize never runs; add a daily in-app maintenance tick |
| `BK-7` | low | fixed | Export snapshot and import upload are spooled on the container's root overlay, not /data |

## The four server cache tables

| id | sev | status | finding |
|---|---|---|---|
| `CACHE-1` | high | fixed | `genre` is an unvalidated browse-cache key; for 69 of 92 browsable connectors it silently caches SEARCH results under a browse key |
| `ADD-3` | high | fixed | Validate browse-cache facets against the connector (genre/sort) and never cache a search fallback |
| `CACHE-2` | medium | fixed | Cover cache has no negative entry: every cover that cannot be downscaled is an upstream fetch + decode per read, and an expired row in that state i... |
| `CACHE-3` | medium | fixed | Rows for a deregistered source are never removed (manhuakey: 40+4 live rows), and a deregistered ADULT source's cached chapter text is served to a ... |
| `ADD-1` | medium | fixed | Add a cache retention sweep (startup + daily) with orphan, age and cap rules |
| `ADD-2` | medium | fixed | Backups should exclude the four cache tables, and a nightly backup job should exist on the VPS |
| `CACHE-4` | low | fixed | _evict_oldest / _evict_lru load full ORM rows (chapter blobs up to 645 KB, paragraphs up to 46 KB) just to delete them |
| `CACHE-5` | low | fixed | Per-series content_rating is stored in source_series_cache but never re-checked against the caller's gate; 57 live rows on NON-mature sources are r... |
| `CACHE-6` | low | fixed | TTL never deletes anything: caches are ~97% of the DB file and are copied into every VACUUM INTO backup |
| `CACHE-7` | low | fixed | novel_chapter_cache bumps last_used_at with a commit on every single chapter read (no throttle), unlike the cover cache |
| `HYP-1` | low | unproven | 7-day novel TTL will force a full re-scrape of immutable chapter text; the 532-chapter bulk fetch of 2026-09-04 expires 2026-09-11 |

## The single SQLite writer

| id | sev | status | finding |
|---|---|---|---|
| `CONC-1` | high | fixed | Federated search runs SQLite SELECT + COMMIT on the event-loop thread |
| `CONC-2` | medium | fixed | Per-series manual check bypasses the sweep lock: overlapping checks double-notify and run connector fetches on the request session |
| `CONC-3` | medium | fixed | Two concurrent first pushes for the same chapter collide on uq_chapter_progress and return 500 |
| `CONC-4` | medium | fixed | A write blocked past busy_timeout surfaces as 500 + dropped keep-alive connection; no busy handling anywhere |
| `CONC-5` | low | partial | Authenticated slow routes hold a pooled DB connection across upstream fetches (image proxy, manifest, series meta, browse page, follow) |
| `CONC-A1` | low | open | Addition: a pooled-engine test fixture so write contention is testable in the suite |
| `CONC-A2` | low | open | Addition (optional): a process-level writer gate for the hot write paths to trim the busy-handler tail |

## Model / API / client drift

| id | sev | status | finding |
|---|---|---|---|
| `C1` | high | fixed | Mobile parses naive-UTC server timestamps as LOCAL time in 8 models; Reading History and Updates screens show times shifted by the device's UTC offset |
| `C2` | medium | open | Server emits every timestamp without a timezone designator; the contract lives only as folklore copied into four client helpers |
| `C3` | low | open | Five dead columns (never written, never read, never serialised) plus collections.cover_url, which the server deliberately omits but mobile still de... |
| `C4` | low | open | followed_series.last_error is write-only: the update sweep records why a check failed, but no serializer, TS type or Dart model ever surfaces it |
| `C5` | low | open | chapter_progress.scroll_offset_px is dead in practice: no client sends a non-zero value and no client reads it back |
| `C6` | low | open | Per-series mature_override can be set but never cleared back to 'inherit' through the API |
| `C7` | low | open | Nullable disagreement: followed_series.content_rating is null on the wire for 2 of 3 live rows, but the web type declares it non-null |
| `C8` | low | open | Reading-time statistic is zero for every existing session and cannot be backfilled; end-of-chapter time is still dropped on tie pushes |

## Query plans and indexes

| id | sev | status | finding |
|---|---|---|---|
| `IDX-1` | medium | fixed | continue_reading window query sorts the profile's whole progress history; a follow-driven top-1 lookup with a recency-ordered index is 16x faster |
| `IDX-5` | medium | partial | Statistics screen runs unbounded whole-history aggregates over append-only reading_sessions on every request |
| `ADD-1` | medium | fixed | Migration 0012_index_tuning: one revision that applies IDX-1..IDX-4 |
| `IDX-2` | low | fixed | update_notifications has five single-column indexes and no scope+recency composite: every listing sorts in a temp b-tree, the unread badge count is... |
| `IDX-3` | low | fixed | Deleting a reading profile full-scans chapter_progress, reading_sessions and followed_series to satisfy ON DELETE CASCADE |
| `IDX-4` | low | fixed | Nine redundant or never-used indexes are maintained on every write |
| `IDX-6` | low | fixed | OCR search loads every FTS hit's full_text for the whole (global) corpus and filters by profile in Python |
| `IDX-7` | low | unproven | ANALYZE / PRAGMA optimize would change plans for the worse on this schema — do not add it blindly |
| `ADD-2` | low | fixed | Retention sweep for the three tables that only ever grow: update_runs, read update_notifications, reading_sessions (post-rollup) |
| `ADD-3` | low | fixed | Keep a query-plan regression suite in CI now that the hot SQL is captured |

## Constraints, cascades and unbounded growth

| id | sev | status | finding |
|---|---|---|---|
| `IL-01` | high | shipped | No scheduled database backup at all; a disk loss on the VPS loses every account, follow, progress row and bookmark |
| `IL-02` | medium | fixed | update_notifications has no UNIQUE on (followed_series_id, chapter_key); a connector that returns a shorter-but-non-empty chapter list re-notifies ... |
| `IL-03` | medium | fixed | Nothing ties (user_id, profile_id) together: the DB accepts a row whose profile belongs to a different account, and every scoped read then loses it |
| `IL-06` | medium | unproven | Every live reading_sessions row has duration 0 and every chapter_progress row has time_spent_seconds 0 - the statistics screen's time-read is struc... |
| `IL-04` | low | fixed | update_runs and update_notifications grow forever; no retention path exists for either |
| `IL-05` | low | open | Cache ceilings are row-based for novel_chapter_cache; worst-case DB size is ~520 MB plus a same-disk VACUUM INTO copy on an 80%-full root disk |
| `IL-07` | low | open | sessions.user_id has no ON DELETE; the user->sessions cascade exists only in Python, and reset-accounts depends on a hand-maintained child-table list |
| `IL-08` | low | unproven | Unfollowing a series leaves its collection_series and profile_series_tags memberships behind |
| `IL-09` | low | open | chapter_ocr is bounded per series only; no global cap, no LRU, and the FTS5 shadow tables double its footprint |

## Per-(user, profile) scoping of every query

| id | sev | status | finding |
|---|---|---|---|
| `ISO-1` | medium | fixed | Profile deletion cascades only via PRAGMA foreign_keys; test engine has it OFF, and SQLite reuses the freed profile id |
| `ISO-2` | medium | fixed | Schema does not tie user_id to profile_id: a row owned by account A but pointing at B's profile is accepted |
| `ISO-3` | low | fixed | Any authenticated member can trigger the instance-wide update sweep and read the global run log |
| `ISO-4` | low | open | chapter_ocr.contributed_by_user_id is a bare integer that outlives reset-accounts while user ids are reused |

## Facts from production, read-only

| id | sev | status | finding |
|---|---|---|---|
| `LDB-01` | high | shipped | No backup exists, but the app already ships a VACUUM INTO snapshot routine that is simply never scheduled |
| `LDB-02` | medium | fixed | Every reading session in production is zero-length: 36/36 rows have started_at == ended_at and all 16 chapter_progress rows have time_spent_seconds... |
| `LDB-03` | medium | unproven | content_rating is NULL on 96% of cached series (1493/1550), including 100% of rows from mixed-content sources mangadex and asurascans |
| `LDB-04` | low | fixed | update_runs has no retention: 104 rows in 3 days and no code path ever deletes one |
| `LDB-05` | low | fixed | 42 startup-triggered update sweeps in 3 days: the backend container is recreated ~14x/day by deploys, and every recreation runs a full sweep |
| `LDB-06` | low | open | 4 connectors have never succeeded in production (coffeemanga and harimanga at 10 consecutive failures; bbato and toonily never OK) |
| `LDB-07` | low | open | source_series_cache is evicted by ORDER BY fetched_at on every browse-page write but has no index on fetched_at |
| `LDB-08` | low | open | The 80%-full disk is the root volume, not the data volume; the pressure is 18.6 GB of reclaimable Docker build cache plus 3.5 GB of .vscode-server |
| `LDB-09` | low | open | novel_chapter_cache became 55% of the database in one afternoon (550 chapters, 11.8 MB, 6 series) and is bounded only by row count, not bytes |

## The 18+ gate on every read path

| id | sev | status | finding |
|---|---|---|---|
| `MG-1` | high | fixed | Collections list gated series (source_id+series_key) and count them, with no 18+ gate |
| `MG-2` | high | fixed | Update sweep resolves the gate from get_settings() so adult-source follows can never be checked |
| `MG-3` | medium | fixed | PATCH /library/series/{id} and re-POST /library/follow echo the full hidden row (title, cover, known_chapters) |
| `MG-4` | medium | fixed | POST /library/follow on a mature source succeeds while the gate is shut (ensure_visible 404 swallowed) |
| `MG-5` | medium | partial | A series' own rating is never applied on general-source browse/detail/chapters/pages |
| `MG-8` | medium | fixed | Gate regression test walks only 5 surfaces; extend it to every read route |
| `MG-6` | low | fixed | Unscoped bucket and new-profile seed read the global gate; fails closed only because the global is False |
| `MG-7` | low | fixed | GET /sources/pins discloses a hidden adult source id via a stale pin |
| `MG-9` | low | open | Single shared row-visibility helper for every table keyed by (source_id, series_key) |

## Schema drift: models vs Alembic vs the live database

| id | sev | status | finding |
|---|---|---|---|
| `MIG-1` | medium | fixed | Boot-time migrations are not atomic on SQLite: a crash mid-migration leaves scratch DDL behind and every subsequent boot fails |
| `MIG-A1` | medium | fixed | Addition: snapshot the DB before any migration actually runs (the only backup the box would have) |
| `MIG-2` | low | open | Five model columns are dead: migrated in 0001, never read or written anywhere in the app |
| `MIG-3` | low | fixed | Downgrade paths destroy data beyond what their docstrings say (0010 and 0002), and a 0002 round-trip deletes every unapplied tag |
| `MIG-4` | low | fixed | env.py has no include_name/include_object filter, so `alembic revision --autogenerate` proposes dropping the FTS5 index |
| `MIG-5` | low | open | Revision id 0008_followed_series_chapter_count is 34 chars, longer than alembic_version.version_num VARCHAR(32) |
| `MIG-A2` | low | open | Addition: make model-vs-migration drift a deploy-time gate with `alembic check` |

## The phone's sqflite store

| id | sev | status | finding |
|---|---|---|---|
| `MS-1` | high | fixed | Resume sweep deletes a chapter that is on screen in a Read-all feed (only the route chapter is claimed) |
| `MS-2` | medium | fixed | savePage writes the blob file before it knows the page row will be accepted; a re-save with different bytes leaks an unreferenced file forever |
| `MS-3` | medium | fixed | Post-commit blob unlink can delete a file another scope re-referenced in the window between commit and unlink (use-after-free across scopes) |
| `MS-4` | medium | fixed | A v3 database opened once by an older build becomes permanently unopenable by the current build (unguarded v1->v2 ALTER TABLE after sqflite's silen... |
| `MS-8` | medium | fixed | Add an orphan-blob garbage collector and a temp-file sweep for the blob tree |
| `MS-5` | low | fixed | A chapter whose manifest shrank between download passes is marked complete but never readable offline (stale extra pages are not pruned) |
| `MS-6` | low | fixed | rowId-keyed mutators are not scope-checked: a store for one (user, profile) can change another scope's chapter row |
| `MS-7` | low | open | idx_saved_pages_chapter duplicates the primary-key autoindex; sizes and index coverage report |
| `MS-9` | low | fixed | Progress outbox grows unbounded while offline; collapse per chapter on enqueue, not only on flush |

## The phone's progress and bookmark outboxes

| id | sev | status | finding |
|---|---|---|---|
| `OUTBOX-1` | medium | fixed | Progress outbox re-sends rows (overlapping flushes, crash replay) and the server SUMS time_spent_seconds — reading time is inflated |
| `OUTBOX-2` | medium | fixed | Bookmark sync in flight across a profile switch merges the OTHER profile's server listing into the old profile's on-device scope (and posts old-sco... |
| `OUTBOX-4` | medium | fixed | Progress outbox is unbounded and every offline save re-reads and JSON-decodes the entire table (O(N) per page turn, O(N²) per session), with no pru... |
| `OUTBOX-ADD-1` | medium | open | Addition: idempotent reading-time by client session id (server + client) so replays and overlaps converge |
| `OUTBOX-3` | low | fixed | One unsendable progress row wedges the whole outbox forever: the server validates the batch as a unit (422) and the client never skips or quarantines |
| `OUTBOX-5` | low | open | Bookmark pull is 'newest 500 incl. tombstones', never a delta — a scope with >500 changes never learns older deletes |
| `OUTBOX-ADD-2` | low | open | Addition: outbox hygiene — collapse-at-enqueue, offline gate, prune-on-profile-removal, and a dead-letter path |

## Reading progress and statistics accounting

| id | sev | status | finding |
|---|---|---|---|
| `PS-1` | medium | fixed | Reading time and pages from non-advancing pushes never reach reading_sessions; re-reads are invisible to statistics and the streak |
| `PS-2` | medium | fixed | Mobile outbox replay double-counts chapter_progress.time_spent_seconds (position is idempotent, time is not) |
| `PS-3` | medium | fixed | Unbounded time_spent_seconds back-dates a session by arbitrary days and invents active days |
| `PS-6` | medium | open | Addition: per-push accumulation gate + drift check between the two time ledgers |
| `PS-4` | low | fixed | clamp_client_clock accepts a far-past last_read_at verbatim: a 1970 row and a 1970 session are stored |
| `PS-5` | low | open | Migration 0006's ix_reading_sessions_series is not used by any statistics statement; the DB has never been ANALYZEd |
| `PS-7` | low | open | Addition: retention/rollup for the append-only reading_sessions table |

## Does the suite actually pin the data layer

| id | sev | status | finding |
|---|---|---|---|
| `TC-1` | high | fixed | Entire test suite runs with PRAGMA foreign_keys=OFF while production runs ON; cascades and FK violations are unobservable in tests |
| `TC-3` | high | fixed | ProgressService._scope user_id predicate is untested (mutant survived 0/2213); unscoped-bucket rows of different accounts would merge |
| `TC-9` | high | fixed | ADDITION: install the production SQLite pragmas on the test engine and pin them with a test |
| `TC-2` | medium | fixed | resolve_mature_gate's user_id ownership check is untested (mutant survived 0/2213) |
| `TC-4` | medium | fixed | A deactivated account's existing sessions are never tested to stop working (mutant survived 0/2213) |
| `TC-5` | medium | fixed | The documented trim/coalesce regression fix in mature_rating_predicate is unpinned (mutant survived 0/2213) |
| `TC-10` | medium | fixed | ADDITION: parametrized ON DELETE CASCADE test over every FK child of reading_profiles and users |
| `TC-6` | low | open | Session expiry is pinned by exactly one service-level test; no HTTP-level pin that an expired token yields 401 |
| `TC-7` | low | open | Several ownership guards hang on a single test (fragile pins) |
| `TC-8` | low | open | update_scheduler's DB writes have no test |
| `TC-11` | low | open | ADDITION: keep the guard-mutation check as a repeatable script |

## The website's localStorage and service worker

| id | sev | status | finding |
|---|---|---|---|
| `WS-1` | high | fixed | Service worker restart hands one tab another profile's API cache (cross-profile leak incl. 18+ listings) |
| `WS-2` | medium | fixed | Corrupted `mm.active-profile` blob leaves the profile gate un-hydrated forever (soft-brick until user finds /profiles) |
| `WS-3` | medium | fixed | Per-profile API cache has no entry cap and no age-out; pressure eviction deletes saved chapters instead |
| `WS-4` | medium | fixed | Per-chapter localStorage keys grow without bound; quota exhaustion silently drops every later preference/progress write |
| `WS-A2` | medium | fixed | Addition: re-publish the worker scope on controllerchange and visibility, and pin it with a restart test |
| `WS-5` | low | unproven | Same-tab profile switch: refetch may reach the worker before the set-scope message |
| `WS-6` | low | open | Update-banner dismissal watermark is tab-global, not per profile |
| `WS-A1` | low | open | Addition: purge a profile's scoped localStorage keys when the profile is forgotten/deleted |


## What 2.7.0 closes, and what it does not

Every `fixed` row above is covered by a test that fails without the change.
The three suites are green: backend 2573, mobile 1591, web 2268.

Three rows say **partial**, and each has a named remainder:

- `IDX-5` — the streak no longer scans all history, but the whole-history
  DISTINCT chapter and series counts still do. Those are not additive across
  days, so no per-day table can answer them; it needs a differently shaped
  table and therefore its own migration.
- `MG-5` — a series' own rating now gates every live browse surface. The two
  global caches in front of browse are not row-gated yet: a page cached by an
  open-gate profile can be served to a shut one. Both are pinned by xfail
  regressions, and the fix is to store the page unfiltered and filter on serve.
- `CONC-5` — the five slow routes in the sources router release their pooled
  connection before the upstream fetch. The two reader-manifest routes, and
  `get_chapter_pages` (whose gate query lives inside the service), still hold.

Two findings that were not in the original 132 were found while fixing these:

- **The reader route split a chapter id at the wrong separator.** Three
  connectors mint ids as `<series>/chapters/<chapter>`, and both route
  parameters are greedy, so the split landed at the last separator instead of
  the route's own. Every chapter on Aurora Scans, BeeHentai and ComicLand
  answered "Chapter not found". This was the owner-reported bug of the day.
- **The test suite read the developer's real database.** `SessionLocal` bound
  its engine at import, so the autouse isolation fixture could not repoint it.
  One test was being served real cached rows and silently skipping the
  connector call it exists to assert on.

That leaves 35 findings `open` and 7 `unproven` — all low severity, all
unscheduled rather than forgotten. `A-1` stays **by design**: registration is
open because the owner wants it open.
