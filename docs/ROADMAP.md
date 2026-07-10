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

## Phase 3 — Public-safe baseline 🔴 Next milestone

The product is deployed publicly at manhwamaniacs.xyz but the code assumes
single-user/no-auth. This milestone closes that gap. It is the recommended next
unit of work (details and file:line findings in the architecture review §9):

- **Authentication in front of the whole API** (first step toward multi-user).
- **Fix the unauthenticated arbitrary-path library import** and gate the
  backup export/import endpoints.
- **Add application CI** (pytest · tsc/eslint/vitest · flutter test on push).
- **Inbound rate limiting.**
- **Deploy hardening:** remove `reload=True`, require `CORS_ORIGINS`, serve the
  APK from a stable path, enforce HTTPS for the mobile client.
- **Finish reconciling docs** with reality (this reset is the start).

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
