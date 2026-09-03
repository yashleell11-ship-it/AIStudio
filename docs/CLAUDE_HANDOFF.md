# Claude Handoff — ManhwaManiacs

**Live:** https://manhwamaniacs.xyz · **App/install:** https://app.manhwamaniacs.xyz
**Repo:** this directory (`aistudio` is the codename; the product is ManhwaManiacs)
**Working branch:** `feat/vps-slim-source-native` — *not* merged to `master` until 1a–1c all land.

> **This file was rewritten 2026-09-03.** Everything before that described a
> different system: a server-side download engine, an int-keyed disk catalog, a
> NAS deployment, and "connectors are frozen". All four are gone. If you find a
> doc that contradicts this one, this one is right — see §6.

---

## 1. What the product is now

A self-hosted manga/manhwa reader and multi-source aggregator, for a household of
a few people (real accounts, each with Netflix-style reading profiles). Three
clients — Next.js web, Flutter mobile, and the raw API — over a FastAPI + SQLite
backend that runs on a 20 GB-budget VPS.

**The defining constraint:** the server never stores chapter images. It scrapes
metadata and proxies page bytes on demand; anything kept for offline reading is
kept **on the client** (browser Cache Storage via a service worker, or the
phone's own store). That is why the download engine was deleted.

## 2. The identity model — read this before touching anything

A series is `(source_id, series_key)`. A chapter is `(source_id, series_key,
chapter_key)`. Keys are **opaque connector strings**: they contain slashes and
percent-encoding, and must be stored raw and exact. Never parse or normalise
them beyond `connectors.ids.fully_unquote` at the HTTP boundary; encode them per
path segment when building URLs (the web client's `encodePathKey` is the
reference).

`chapter_number` (float, nullable) rides alongside every progress, notification
and cache row. It is the only axis that is stable *across* sources, so it is what
any future "this source died, follow it somewhere else" migration would map by.

## 3. Where things are

| Concern | Location |
|---|---|
| The library (a follow) | `followed_series` — per `(user_id, profile_id)`, NOT NULL both |
| Reading position | `chapter_progress` — furthest-wins merge, never last-write-wins |
| Connector metadata | `source_series_cache` — a TTL cache, global, safe to purge |
| Dialogue text | `chapter_ocr` — global per chapter (like `source_health`), populated by clients |
| Backend services | `followed_series_service`, `progress_service`, `source_cache_service`, `reader_service`, `ocr_ingest_service`, `ocr_search`, `update_service` |
| Web offline store | `frontend/public/sw.js` + `sw-policy.js` (the SW is the only writer of Cache Storage) |
| Deploy | `ops/vps/` — `docker-compose.yml`, `deploy.sh` (on the VPS), `push.sh` (from the laptop) |

Connectors (`backend/connectors/**`) were untouched by the rewrite and still
work. They are no longer "frozen" in the old sense — but they are also not where
current work is.

## 4. Rules that will bite you if you break them

1. **Per-profile isolation is the security boundary.** Every read filters on
   `(user_id, profile_id)`; every mutating route depends on
   `require_profile_context`. There is no household-shared catalog any more, so
   there is no "everyone can see it" fallback to lean on.
2. **Progress merges furthest-wins.** `(chapter_number, last_page)` only moves
   forward, `last_read_at` is a tie-break only, `is_completed` is sticky. LWW
   silently rewinds a reader mid-series and they do not notice for hours.
3. **Nothing chapter-sized goes on the server disk.** If a change would cache
   page bytes server-side, it is the wrong change.
4. **Registration stays closed.** `MM_REGISTRATION_ENABLED=false`. An empty
   users table on a public host is an open admin takeover.
5. **The mobile app is sideloaded on iOS**, so: downloads are foreground-only,
   the keychain can be wiped by a re-sign (never key the offline store to it),
   and adding a CocoaPod means a lockfile only a cloud Mac can regenerate.

## 5. Current state and what is next

- **1a — backend:** done. 600 tests green, deployed.
- **1b — web client:** source-native, reader experience pass (cinema mode,
  seamless pages and chapter transitions, continue-hero, ambient mood tint),
  offline renamed to Downloads. Finishing OCR/updates/admin polish + e2e.
- **1c — mobile:** spec written (`docs/superpowers/specs/2026-09-03-mobile-source-native-design.md`),
  not started. Blocked on the user for GitHub push auth and repo visibility
  before the iOS cloud build can run.

The specs under `docs/superpowers/specs/` are the authoritative plans. Start
there, not here.

## 6. Docs you should distrust

- `ARCHITECTURE_REVIEW_2026-07-11.md` — a good review *of a system that no
  longer exists*. Historically interesting; architecturally obsolete.
- `OFFLINE_READING.md` — the transport/store/eviction design is still the
  reference for the phone, but its NAS-primary framing is superseded.
- `SOURCE_ROLLOUT_HANDOFF.md`, `CONNECTOR_STATUS.md` — connector-era, unverified
  against the current tree.
- `ROADMAP.md` — has a correct 2026-09-03 pivot section on top of older phases.
