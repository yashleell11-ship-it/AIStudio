# ManhwaManiacs — Development Roadmap

> **This roadmap was reset on 2026-07-11** to reflect what the product actually
> is and two ratified product decisions (see §"Ratified decisions" below). The
> earlier roadmap's Phases 3–5 ("AI Layer", "Knowledge Graph", "Creation
> Studio") described an internal local-AI *creation* platform that was never
> built and is **no longer a goal**; those documents are archived under
> [`docs/archive/ai-studio/`](archive/ai-studio/README.md).
>
> The authoritative, prioritized engineering plan lives in
> [`ARCHITECTURE_REVIEW_2026-07-11.md`](ARCHITECTURE_REVIEW_2026-07-11.md) §9.
> This file is the product-level narrative; that report is the execution list.

---

## 2026-09-03 — VPS slim-down pivot

The product is moving off the household NAS onto a **VPS with ≤20 GB of disk**.
Chapter images are the only unbounded thing and cannot live on that box, so:

- **Server-side downloads are removed entirely.** The `DownloadManager`, the
  `/downloads` volume, the disk scanner, library import, and the server-side OCR
  runner are all deleted. The backend becomes a connector + image-proxy +
  metadata store.
- **Downloads are client-side only.** Phone and web clients pull chapter bytes
  directly through the existing source image proxy and store them on-device.
- **The backend is rebuilt source-native.** Everything keys on
  `(source_id, series_key, chapter_key)` opaque connector strings; the catalog
  tables (`libraries`/`series`/`chapters`/`pages`/`downloads`/…) are dropped and
  the DB is wiped with a fresh Alembic baseline.
- **Multi-user is kept and finished.** Multiple accounts, each with multiple
  profiles, with **per-profile** data isolation (follows, progress, collections,
  bookmarks, notifications). This supersedes the "Phase 4 future" framing below.
- **OCR dialogue search is kept, client-driven.** The phone runs OCR on
  downloaded pages and uploads the text; the server only ingests + searches.

Three sub-projects, all on branch `feat/vps-slim-source-native`, not merged to
`main` until all three land: **1a backend** (this pivot), **1b web client**,
**1c mobile client**.

Source of truth:
[`superpowers/specs/2026-09-03-backend-source-native-design.md`](superpowers/specs/2026-09-03-backend-source-native-design.md).
This also supersedes the NAS-primary model in
[`OFFLINE_READING.md`](OFFLINE_READING.md).

---

## What ManhwaManiacs is

A self-hosted **manga / manhwa / manhua reader and multi-source aggregator**:
library management, a webtoon/paged reader, multi-source search + downloads,
OCR dialogue search, and automatic update tracking. Three clients (Next.js web,
Flutter Android, and the raw API) over a FastAPI + SQLite backend.

## Ratified decisions (2026-07-11)

1. **Target access model: real multi-user.** The product is intended to grow
   into full user accounts with per-user ownership (auth + `user_id` on owned
   rows), not single-user-no-auth. This is a large, schema-wide change and is
   sequenced on the roadmap below — it is *not* yet implemented.
2. **AI is a product capability, not an internal platform.** No local models, no
   Ollama/ComfyUI, no in-app AI creation studio. AI features consume **external
   AI APIs** when built: recommendations, personalized home feed, similar-series
   suggestions, reading/chapter/character/series summaries, search improvements,
   tag generation, metadata enrichment, smart collections, and continue-reading
   suggestions.

---

## Phase 1 — Foundation ✅ Complete

Feature-based frontend structure, design system, app shell + nav, keyboard
shortcut layer, typed API client, TanStack Query + Zustand, backend clean
architecture (`routes/ → services/ → core/`), settings loader, uniform error
envelope, CORS.

## Phase 2 — Library + Reader ✅ Largely complete

Library scanner + data layer, image serving, the reader (webtoon + paged),
reading progress + continue-reading, multi-source search + connectors, the
download engine, OCR dialogue search, and automatic update tracking are all
built and shipping. Remaining polish is tracked as Medium/Low items in the
architecture review.

---

## Phase 3 — Public-safe baseline ✅ Complete

The product is deployed publicly at manhwamaniacs.xyz but the code assumed
single-user/no-auth. This milestone closed that gap and made the public instance
defensible. Full details of the auth model live in **[docs/AUTH.md](AUTH.md)**.

- ✅ **Authentication in front of the whole API.** A single global gate
  (`enforce_authentication`, wired on `api_router`) requires a valid session on
  every route except a small public allowlist (landing/health, `/auth/login`,
  `/auth/register`, `/auth/bootstrap-status`, and the `/app/*` APK distribution
  surface). Opaque sessions: httpOnly cookie for web, `Authorization: Bearer`
  for mobile.
- ✅ **Destructive/admin ops require an admin session.** The `MM_ADMIN_TOKEN`
  header stop-gap and `core/security.py` are gone; `/library/import`,
  `/backup/export`, `/backup/import`, `/backup/pending` now depend on
  `require_admin_user`. The first registered account bootstraps as admin.
- ✅ **Library import path containment.** Imports are constrained to an
  allowlist (`MM_IMPORT_ROOTS` ∪ registered library roots ∪ the downloads
  path); arbitrary host paths such as `/` or `/etc` are rejected with 403.
- ✅ **Application CI** (`.forgejo/workflows/ci.yml`): backend pytest,
  frontend tsc/eslint/vitest/build, and mobile `flutter analyze`/`flutter test`
  on every push to a mainline branch and every pull request.
- ✅ **Inbound rate limiting** (slowapi) on the abusable endpoints — auth,
  library/backup imports, and source browse/search/image — keyed per client IP.
- ✅ **Client auth integration:** web (Next.js) login/register/guard with 401
  handling and first-admin bootstrap UX; mobile (Flutter) bearer-token storage,
  401 redirect, and HTTPS-only base URL enforcement in release builds.
- ✅ **Docs reconciled** with reality (this section + docs/AUTH.md).

Deliberately **not** in this milestone (tracked for Phase 4): per-user
authorization on every read (rows are still visible to any authenticated user;
only ownership *writes* are scoped), connector expansion, and new sources.

## Phase 4 — Multi-user foundation 🟠

Turn the "single-user local-first" data model into a real multi-user one:

- User accounts, sessions, and authorization.
- `user_id` ownership on user-owned rows (reading progress, bookmarks,
  collections, trackers, downloads); shared vs. per-user library semantics.
- A **repository/service seam** so persistence is swappable and unit-testable
  (prerequisite for a future Postgres migration).
- **Process-safe background workers** (leader election or externalized
  schedulers) so the app can run more than one worker.
- **Alembic** migrations replacing the boot-time hand-rolled migrations.

## Phase 5 — AI product features (external APIs) 🟡

Built *only* on external AI APIs, incrementally, each behind the same clean
service seam:

- Recommendations, personalized home feed, similar-series suggestions.
- Reading / chapter / character / series summaries (built on existing OCR text).
- Search improvements, tag generation, metadata enrichment.
- Smart collections and continue-reading suggestions.

## Phase 6 — Scale & polish 🟢

Shared API contract (types generated from OpenAPI + a cross-tier contract test),
frontend test coverage, pagination for library grids, mobile offline/local
storage, and a possible Postgres migration once the repository seam lands.

---

## Recurring rules (every phase)

1. Builds clean (`npm run build`), type-checks clean (`tsc --noEmit`), lint clean.
2. No placeholder code; no TODO comments in committed code.
3. No regressions in layer separation (routes → services → core; no business
   logic in routes).
4. New endpoints return the standard error envelope.
5. Design tokens only — no hardcoded colors.
6. `docs/STRUCTURE.md` updated when the file layout changes.
7. **No internal AI platform.** AI features call external APIs (ratified decision 2).
