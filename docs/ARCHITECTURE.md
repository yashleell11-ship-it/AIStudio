# Architecture

One page. ManhwaManiacs is a self-hosted manga/manhwa reader and multi-source
aggregator for a small household of real accounts, deployed on a single VPS
with a deliberately small disk budget. For the how-and-why behind the current
shape, see the specs linked at the bottom — this page is the map, not the
territory.

## What runs where

| Piece | What it is | Where |
|---|---|---|
| `backend/` | FastAPI + SQLAlchemy app: connectors, auth, library/progress/OCR/updates services, image proxy | `manhwamaniacs-backend` container, VPS |
| `frontend/` | Next.js 16 / React 19 web client, SSR + a service-worker offline store | `manhwamaniacs-frontend` container, VPS |
| `mobile/` | Flutter app (Android + sideloaded iOS), talks to the backend directly over HTTPS | end-user phones, not the VPS |
| Metadata DB | SQLite (`manhwamaniacs.db`) — users, follows, progress, caches. No chapter images. | `/srv/manhwamaniacs/data` on the VPS's dedicated 50 GB disk |
| Edge | Caddy + cloudflared, shared with an unrelated Minecraft-bots stack (co-tenant on the `mcbots_bots` docker network) | VPS |

Both app containers build from `ops/vps/docker-compose.yml` and join that
shared `edge` network; nothing binds a host port directly. Details, including
the manual steps that aren't automated yet: **[VPS_OPERATIONS.md](VPS_OPERATIONS.md)**.

## The defining constraint

**The server never stores chapter images.** It scrapes metadata from source
websites and proxies page bytes on demand; nothing chapter-sized touches
`/srv/manhwamaniacs`. That's a hard budget constraint (20 GB for the app, most
of it free by design) as much as a design choice — the previous NAS deployment
had a server-side download engine and an unbounded `/downloads` volume, and
both were deleted outright rather than shrunk. If a change would cache page
bytes server-side, it's the wrong change.

Anything a reader wants offline is kept **on the client**: the browser's Cache
Storage (via a service worker) on web, or an on-device SQLite store plus a
content-addressed blob tree on the phone.

## Data model, in one paragraph

Identity is source-native, not a local catalog. A series is the pair
`(source_id, series_key)`; a chapter is `(source_id, series_key, chapter_key)`.
`series_key`/`chapter_key` are **opaque connector strings** — they can contain
slashes and percent-encoding and must be stored and passed through raw and
exact, never parsed. A float `chapter_number` rides alongside every
follow/progress/cache/notification row as the one axis that's stable *across*
sources (used for a future "this source died, follow it somewhere else"
migration). The library is `followed_series`, one row per `(user, profile,
source, series)` — being in the library **is** having a follow row; there's no
separate downloaded/imported state on the server. Reading position lives in
`chapter_progress` and merges **furthest-wins**, never last-write-wins: a
`(chapter_number, last_page)` pair only moves forward, so a stale offline
client replaying old progress can't rewind a reader mid-series. Everything
that used to be a shared household catalog is now scoped to
`(user_id, profile_id)` — each reading profile has its own follows, progress,
collections, bookmarks and notifications, with no cross-profile visibility by
default. Full schema: **[backend-source-native-design.md §3](superpowers/specs/2026-09-03-backend-source-native-design.md#3-target-schema-fresh-alembic-baseline)**,
ground truth as ever is `backend/database/models.py`.

## How a chapter gets to a screen

**Web:** browser → Next.js (same-origin `/api/*`, rewritten to the backend
container internally) → `GET /reader/chapter/manifest?source=&series=&chapter=`
for the page list, then each page loads through
`GET /sources/{source}/pages/{page:path}/image`, a proxy straight to the
source site. For offline, the existing service-worker system
(`frontend/public/sw.js`) caches those same URLs into browser Cache Storage —
repointed at the new endpoints, not rewritten.

**Mobile:** Flutter app → the backend directly at `app.manhwamaniacs.xyz`
(no separate API host) → same manifest + per-page-image-proxy flow. A download
queue (`mobile/lib/features/downloads/`) fetches every page through
`ChapterPageFetcher` and writes it into a content-addressed blob store under
`getApplicationSupportDirectory()` (sqflite for metadata, never
`getTemporaryDirectory()` — iOS purges that under pressure). Downloads are
**foreground-only**: a sideloaded iOS build has no dependable background
execution. A read chapter's on-device copy is auto-evicted 48 hours after it's
finished (pinned series exempt); reading progress survives that eviction and
resyncs to the server through a local outbox
(`POST /reader/progress/batch`) once back online. Deep design reference:
**[OFFLINE_READING.md](OFFLINE_READING.md)**.

**Neither client ever gets chapter bytes from server disk** — both paths above
terminate at the live source website through the same image proxy; the only
thing that differs is whether a client keeps a copy afterward.

## Auth

Sessions are opaque tokens (argon2id-hashed passwords, SHA-256-hashed session
tokens); web gets an httpOnly cookie, mobile gets the same token as a bearer
header. Registration is **closed by default**
(`MM_REGISTRATION_ENABLED=false` in `ops/vps/docker-compose.yml`) — the owner
account is created out-of-band with `ops/vps/deploy.sh create-owner`. A
household can opt into self-service signup by enabling registration and
setting an invite code; a time-boxed **bootstrap window**
(`MM_BOOTSTRAP_WINDOW_MINUTES`, default 30) additionally lets the very first
registration on an empty users table claim the instance as admin, so a wiped
database on a public host isn't an indefinite open-admin window. Exactly one
admin is enforced at the database level (a partial unique index on
`users.is_admin`). Full model: **[AUTH.md](AUTH.md)**.

## Sources

Connectors under `backend/connectors/` scrape upstream manga/manhwa sites —
dozens of them, mostly generated from a shared "Madara" WordPress-theme
factory config (`connectors/catalog.py`) plus a handful of hand-written
connectors for sites that need bespoke logic (MangaDex's official API,
Toonily's Cloudflare handling, etc.). The rest of the app depends only on the
normalized `connectors/models.py` shapes, never on a specific site. There is
no server-side "local library" import path any more — everything a user reads
comes from a live connector.

## Deploy

```
laptop: ops/vps/push.sh [frontend|backend|apk]   # builds, rsyncs, rebuilds remotely
VPS:    ops/vps/deploy.sh {deploy|create-owner|reset-accounts|set-invite-code|logs|edge}
```

The VPS checkout has no `.git` — code is rsynced, not cloned, because this
laptop currently has no push credentials to the private GitHub mirror used for
the iOS cloud-Mac build. The commit id travels in a `.deploy-info` file so a
running container can still be traced to a revision. Full operator page,
including what's still manual: **[VPS_OPERATIONS.md](VPS_OPERATIONS.md)**.

iOS is distributed by **sideloading via SideStore**: GitHub Actions builds the
IPA on a cloud Mac and publishes it as a GitHub release; a VPS cron fetches it
and the backend serves `/app/source.json` for SideStore's OTA update check.
Re-signing every ~7 days is expected and normal; app data (including the
on-device chapter store) survives a re-sign as long as nothing is keyed to the
keychain, which is why the download store deliberately never uses
`flutter_secure_storage`. Android ships as a plain APK, built locally and
pushed to `/srv/manhwamaniacs/apk/`, served from the same `app.manhwamaniacs.xyz`
host.

## Where to go next

- [VPS_OPERATIONS.md](VPS_OPERATIONS.md) — the operator's page: hosts, how to ship, manual steps
- [AUTH.md](AUTH.md) — session/registration/admin model in full
- [OFFLINE_READING.md](OFFLINE_READING.md) — the on-device store design
- [SOURCES.md](SOURCES.md) — the connector system
- [ROADMAP.md](ROADMAP.md) — product narrative and phase history
- [superpowers/specs/](superpowers/specs/) — the three 2026-09-03 pivot specs (backend, web, mobile), the source of truth this page summarizes
- [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md) — where an agent picking this up should start
