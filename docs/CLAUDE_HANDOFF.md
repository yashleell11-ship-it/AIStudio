# Claude Handoff — Product & Platform (Connectors Frozen)

Use this when handing work to **Claude** (architecture, backend services, frontend, mobile, docs).
**Do not use** `docs/SOURCE_ROLLOUT_HANDOFF.md` for Claude sessions — that is Cursor-only connector work.

**Live site:** https://manhwamaniacs.xyz  
**Repo:** `/home/yash/dev/aistudio` · **Branch:** `develop`

---

## 1. Connectors are DONE (do not touch)

Online source connectors are **complete for this phase**. Another agent (Cursor) owns any remaining source fixes later.

### You must NOT

- Edit `backend/connectors/**` (except if a bug blocks unrelated work — ask the user first)
- Edit `backend/connectors/catalog.py`, `registry.py`, `excluded.py`, `madara/**`
- Add/remove/register connectors
- Run source rollout probes or deploy backend for connector fixes
- Read or follow `.cursor/rules/source-connector-rollout.mdc` or `docs/SOURCE_ROLLOUT_HANDOFF.md`

### Assume connectors work

- `GET /sources` lists installed connectors
- Browse → series → chapters → reader flows are implemented per source
- HariManga, Hentai20, ComicsValley, and the custom connector batch are deployed
- Remaining broken sources in the grid will be fixed **later by Cursor**, not by you

If the user reports a broken source, **acknowledge and defer** to the connector rollout — do not fix it in this session.

---

## 2. What Claude already delivered (2026-07-11)

- [`docs/ARCHITECTURE_REVIEW_2026-07-11.md`](ARCHITECTURE_REVIEW_2026-07-11.md) — full codebase review
- [`docs/ROADMAP.md`](ROADMAP.md) — reset to real product scope; ratified decisions
- Phase 3 **Public-safe baseline** documented as complete (auth, CI, rate limits)
- Dead AI platform code removed (`/ai/chat`, Ollama, placeholder `/create` + `/ai` pages)
- Safe cleanups: `frontend/src/config/env.ts`, library hooks cache key, dead backend helpers

**Your job now:** execute **Phase 4+** and integration polish from the architecture review — not connectors.

---

## 3. Authoritative reading order

1. [`frontend/AGENTS.md`](../frontend/AGENTS.md) — global rules (no local AI, no Creation Studio)
2. [`docs/ROADMAP.md`](ROADMAP.md) — product phases
3. [`docs/ARCHITECTURE_REVIEW_2026-07-11.md`](ARCHITECTURE_REVIEW_2026-07-11.md) — §9 priority roadmap
4. [`docs/AUTH.md`](AUTH.md) — current auth model (global gate; per-user reads still shared)
5. [`docs/SOURCES.md`](SOURCES.md) — how sources API works (read-only; don't change connectors)

Ignore archived AI-studio docs unless the user explicitly revives that direction.

---

## 4. Recommended work order (pick one milestone per session)

| Priority | Milestone | Scope |
|----------|-----------|--------|
| 🟠 P1 | **Integration polish** | ✅ Done (UpdateBanner, OCR UI, updates 409 verified) |
| 🟠 P2 | **Phase 4 start** | Repository seam design + first extraction; Alembic baseline |
| 🟡 P3 | **Phase 6 polish** | OpenAPI → TS types, frontend vitest/jsdom, Playwright skeleton |
| 🟡 P4 | **Reader/library bugs** | `SourceReader` ↔ `sources/hooks` cycle, `ChapterReader` scroll sync |
| 🟡 P5 | **Netflix-style profiles (web + mobile)** | Profile picker, genre mood themes, animations, persistent login — see §5.8 |
| 🔴 P6 | **Reader seamless pages** | Remove black gaps/lines between pages on scroll — see §5.9 |
| 🟡 P7 | **Product polish backlog** | Home, reader, library, updates features — see §5.10 |
| 🟠 P9 | **app.manhwamaniacs.xyz** | APK subdomain + deploy pipeline — see §5.13 |
| 🟠 P10 | **Series UX + mood shell + download-while-reading** | §5.15 |

---

## 5. Copy-paste prompts

### 5.1 Master session prompt (paste first every time)

```
You are working on ManhwaManiacs at /home/yash/dev/aistudio (branch develop).

READ FIRST:
- docs/CLAUDE_HANDOFF.md
- frontend/AGENTS.md
- docs/ROADMAP.md
- docs/ARCHITECTURE_REVIEW_2026-07-11.md §9

CONNECTORS ARE FROZEN — DO NOT TOUCH:
- No edits under backend/connectors/
- No catalog/registry/excluded/madara changes
- No source rollout, probing, or connector deploys
- Assume all sources are done; defer source bugs to Cursor

Your scope: product platform — auth/multi-user, services, frontend/mobile UI, tests, docs, deploy hardening.

Do not commit unless I ask.
Do not reintroduce Ollama, Creation Studio, or knowledge-graph features.

Tell me which milestone you will tackle before coding.
```

### 5.2 Integration polish (quick wins)

```
ManhwaManiacs — integration polish sprint. Connectors are FROZEN (see docs/CLAUDE_HANDOFF.md).

Fix these open items from docs/archive/PRODUCTION_READINESS_REPORT.md:

1. backend/routes/updates.py ~line 149 — when check already running, return 409 instead of synchronous run_check() on the HTTP thread
2. frontend features/update/ — implement UpdateBanner per docs/archive/specs/SPEC_CURSOR_CHAT2_AUTO_UPDATE.md; wire into app-shell (self-contained banner)
3. Optional: OCR search UI — backend routes/ocr.py exists; add minimal frontend features/ocr/ for queue status + dialogue search (read SPEC_KIMI_AGENT1 if needed)

Verify: backend pytest for updates route; frontend npm run typecheck && npm run build.

Do NOT touch backend/connectors/.
Do not commit unless I ask.
```

### 5.3 Phase 4 — Multi-user foundation (design + first slice)

```
ManhwaManiacs Phase 4 — multi-user foundation. Connectors FROZEN (docs/CLAUDE_HANDOFF.md).

Goal: move from "any authenticated user sees all rows" to per-user ownership on user-owned data.

Read: docs/ROADMAP.md Phase 4, docs/AUTH.md, ARCHITECTURE_REVIEW §9 items 5–8.

Deliver in this session (pick achievable slice):
1. Design doc: which tables get user_id, shared vs per-user library semantics
2. Alembic baseline migration from current models.py (no connector schema changes)
3. OR: first repository interface extracting one service (e.g. reading progress) from raw SQLAlchemy

Do NOT modify backend/connectors/.
Do not commit unless I ask.
```

### 5.4 Phase 6 — API contract + frontend tests

```
ManhwaManiacs Phase 6 polish. Connectors FROZEN.

1. Export OpenAPI from FastAPI; generate TypeScript types for frontend (or document manual sync process)
2. Add one cross-tier contract test (backend response shape ↔ frontend type)
3. Frontend: vitest jsdom config; tests for services/http.ts and ui-store
4. Playwright: minimal e2e/ config + smoke test (login → library loads)

Do NOT touch backend/connectors/.
Do not commit unless I ask.
```

### 5.5 Backend performance — download re-index

```
ManhwaManiacs backend only. Connectors FROZEN.

Fix O(n²) download library re-index in download_manager.py (~line 650): incremental index on completion instead of full rescan.

Add/adjust pytest coverage. Run: cd backend && python -m pytest tests/ -q -k download

Do NOT touch backend/connectors/.
Do not commit unless I ask.
```

### 5.6 Docs reconciliation

```
ManhwaManiacs documentation pass. Connectors FROZEN.

Reconcile docs with code:
- Regenerate or rewrite docs/API.md from live OpenAPI (or add docs/API.generated.md)
- Ensure README, ROADMAP, AUTH, SOURCES match production
- Move or clearly mark archived ai-studio docs as non-goals

Do NOT edit connector rollout docs except a one-line pointer to CLAUDE_HANDOFF.md.
Do not commit unless I ask.
```

### 5.7 Reader / sources UI (no connector logic)

```
ManhwaManiacs frontend — reader/sources integration. Connectors FROZEN.

Fix without changing backend/connectors/:
1. Break import cycle: features/reader/components/SourceReader.tsx ↔ features/sources/hooks.ts
2. ChapterReader scroll sync — move syncChapterScroll out of render into useLayoutEffect (see PRODUCTION_READINESS_REPORT B4)

Run: cd frontend && npm run typecheck && npm run lint && npm run test

Do not commit unless I ask.
```

### 5.8 Mobile + Web — Netflix-style reading profiles (full feature)

> **Scope note (2026-07-11):** Same experience on **web and mobile**. Do not ship
> mobile-only. **Session persistence:** users who are already logged in must stay
> logged in across visits — never force re-entering email/password on every open.
> Profile picker runs *after* an existing session is restored, not instead of it.

```
ManhwaManiacs — mobile Netflix-style reading profiles. Connectors FROZEN (docs/CLAUDE_HANDOFF.md).

## Objective

After login, show a Netflix-style **Who's reading?** screen before the main app.
Each profile has a name, avatar, and a **reading mood / genre** that tints the app
background subtly for that session. Animations should feel premium (staggered entrance,
profile focus on hover/tap, smooth transition into the home shell) — but colors must
stay **muted and reading-friendly** (never bright/neon; low saturation, dark-base tints).

## User-facing requirements

0. **Stay signed in:** Web uses httpOnly `mm_session` cookie; mobile uses secure-
   storage bearer token. On cold start, validate stored session via `/auth/me`
   before showing login. Only show login when session is missing or expired.
   Profile picker is a gate *after* auth, not a replacement for remembered login.
   Extend session TTL / "Remember me" if users still get logged out too often.

1. **Profile picker screen** (web + mobile, after auth, before dashboard):
   - Headline like "What are you going to read today?" (or similar warm copy)
   - Horizontal row of profile avatars (Netflix-style circles/cards)
   - **Add profile** tile (dashed or "+" card) — max 5 profiles per account
   - Staggered fade+scale entrance animation on load (profiles appear one-by-one)

2. **Profile selection animation**:
   - On tap: selected profile scales up slightly, others dim/blur, background
     cross-fades to that profile's mood tint, then route animates into home
   - Use Hero or custom shared-element if it looks good; keep 60fps

3. **Genre / mood → background theme** (per profile, user picks at create/edit):
   - Romantic → soft dusty rose tint on dark base (#030507 family)
   - Action → muted burgundy / deep red-brown tint
   - Comedy → warm amber-brown (not yellow)
   - Horror → blue-gray / desaturated purple
   - Slice of life → sage green-gray
   - Fantasy → deep teal-violet
   - Default / All genres → existing AppColors.bg (no tint)
   - Tints apply to shell background + profile picker only; reader keeps its own
     Dark/AMOLED/Paper modes unchanged

4. **Profile management**:
   - Create: name (required), pick avatar icon/color, pick mood/genre
   - Edit / delete from Settings → Profiles (or long-press on picker)
   - Switch profile: Settings or avatar chip in app bar → back to picker

5. **Persistence** (you decide best approach; document in code comment):
   - **Preferred:** backend `reading_profiles` table scoped to `user_id` (Phase 4
     slice) + `X-Profile-Id` header or query param on API calls so progress/bookmarks
     can eventually be per-profile
   - **Acceptable v1:** local-only in secure storage / shared prefs if backend slice
     is too large for one session — but design models so backend migration is easy

## Technical guidance

Read first:
- mobile/lib/app/router/app_router.dart — insert profile gate after AuthAuthenticated
- frontend/src/features/auth/ — web session guard; mirror profile gate in app shell
- mobile/lib/app/theme/app_colors.dart — extend with ProfileMoodTheme tokens, not inline hex
- mobile/lib/features/auth/ — auth flow; do not break login/register/splash
- mobile/lib/shared/widgets/scroll_reveal.dart — reuse motion language if useful
- docs/AUTH.md, docs/ROADMAP.md Phase 4 — user_id ownership semantics

Implementation structure (feature-first):
- **Mobile:** mobile/lib/features/profiles/ — models, providers, screens, widgets, repository
- **Web:** frontend/src/features/profiles/ — same UX parity (picker, add, mood themes, animations)
- ProfileMood enum + theme resolver (bg gradient, accent wash, avatar ring color)
- Router: `/profiles` (picker), `/profiles/create`, `/profiles/edit/:id`
- Redirect: authenticated && no activeProfile → `/profiles`; else → home
- Widget tests for picker + mood theme resolver; keep flutter test green

## Animation spec (target feel)

- Picker load: 300–400ms stagger, 80ms between profiles, easeOutCubic
- Profile focus: scale 1.0 → 1.08, subtle glow ring in mood color
- Enter app: 400ms fade + slight zoom-out of picker, cross-fade shell bg tint
- Respect reduced-motion: skip stagger, instant transitions

## Do NOT

- Touch backend/connectors/
- Use bright/saturated backgrounds (reading app, not game UI)
- Break existing 348+ flutter tests
- Commit unless I ask

## Verify

cd mobile && flutter analyze lib && flutter test

## Deliverable summary

When done, report: files added/changed, mood palette table, router flow diagram,
backend vs local persistence choice, and screenshots description for picker + one
mood theme applied to home.
```

### 5.9 Reader — seamless page scroll (no gaps/lines between pages)

> **User-reported bug:** When scrolling page 1 → page 2 in vertical/webtoon mode,
> visible **black lines/gaps** appear between pages (see screenshot in chat). Reading
> should feel like one continuous strip — pages butt together with **zero separator**.

```
ManhwaManiacs — reader seamless pages fix. Connectors FROZEN.

## Problem

Vertical scroll reader shows black gaps/lines between consecutive pages (e.g. page 1
→ page 2). User wants continuous webtoon-style flow — no visible seams.

## Likely causes (investigate both tiers)

**Mobile** (`mobile/lib/features/reader/widgets/reader_content.dart`):
- `Padding(padding: EdgeInsets.only(bottom: AppSpacing.xs))` between vertical pages (~4px)
- List padding / backdrop showing through between images
- Aspect-ratio letterboxing leaving black bars that read as "lines"
- Virtualized list estimate vs actual height mismatch causing scroll gaps

**Web** (`frontend/src/features/reader/components/VirtualPageList.tsx`):
- `pb-1` on each `VirtualPageRow` (~4px gap)
- PageImage letterboxing / max-width constraints
- Virtualizer `estimateSize` vs measured height drift

## Fix requirements (web + mobile)

1. **Zero gap mode** for vertical/webtoon scroll: remove inter-page padding/margin;
   pages stack flush edge-to-edge.
2. Optional **Settings → Reader → Page gap** toggle (default OFF) for users who want
   a thin separator — only when explicitly enabled.
3. Images should **fill width**; if aspect ratio leaves vertical letterboxing, use
   reader backdrop color (not harsh black seam) or bleed adjacent page color.
4. Prefetch next page so scroll never "hits air" between images.
5. Add regression test or golden description: two pages scroll with no visible gap
   in vertical mode.

## Verify

cd mobile && flutter analyze lib && flutter test
cd frontend && npm run typecheck && npm run test

Do NOT touch backend/connectors/.
Do not commit unless I ask.
```

### 5.10 Product polish backlog (user-prioritized features)

> Implement **one slice per session**. Web + mobile parity unless noted.
> Connectors FROZEN. Reuse `ScrollReveal` motion language where relevant.

| # | Feature | Scope |
|---|---------|-------|
| 1 | **Continue hero** — big cover + one-tap resume exact page on home open | Web + mobile |
| 2 | **Tonight's read** — profile mood picks 3–5 daily suggestions with soft shuffle | Web + mobile |
| 3 | **"Because you read X" rails** — Netflix-style horizontal rows (similar, same author) | Web + mobile |
| 5 | **Seamless chapter transition** — end-of-chapter card slides up; prefetch next ch. | Web + mobile |
| 6 | **Ambient reader tint** — ultra-subtle mood wash in reader margins (not on page) | Web + mobile |
| 7 | **Page-turn haptic weight** — stronger haptic at chapter boundaries | Mobile |
| 8 | **Cinema mode** — hide chrome; page counter fades in only on pause | Web + mobile |
| 9 | **Smart brightness** — per-profile brightness + auto-dim idle; **Settings** | Mobile |
| 10 | **Smart shelves** — auto shelves: Reading, Caught up, On hiatus, Finished | Web + mobile |
| 11 | **Cover stack** — long-press series → fanned recent chapter covers, quick jump | Web + mobile |
| 12 | **Collection posters** — mosaic thumbnail from 4 series covers | Web + mobile |
| 13 | **Unread pulse** — soft dot on cards when new chapters; one pulse on app open | Web + mobile |
| 16 | **Profile handoff** — quick profile switch without logout (Netflix pass-the-phone) | Web + mobile |
| 18 | **Offline shelf** — per-profile row of everything downloaded; works server-down | Web + mobile |
| 19 | **Wi‑Fi smart queue** — "Download next N chapters of all in-progress" overnight | Web + mobile |
| 20 | **Chapter drop animation** — new update card slides in with one-time soft shimmer | Web + mobile |
| 21 | **"While you were away"** — after 3+ days: summary screen, swipe to dismiss | Web + mobile |
| 22 | **Per-profile notification prefs** — action profile = all updates; romance = favorites only | Web + mobile |
| 23 | **First-run taste picker** — pick 3 genres from cover tiles; seeds recs + mood | Web + mobile (onboarding) |
| 26 | **Pull-to-refresh personality** — manga page-corner flip instead of generic spinner | Web + mobile |
| 27 | **Seasonal micro-themes** — optional cooler/warmer dark base; still readable | Web + mobile |

**Session prompt template (pick one #):**

```
ManhwaManiacs — product polish slice #{N} from docs/CLAUDE_HANDOFF.md §5.10.
Connectors FROZEN. Web + mobile parity. One feature, done well.
Read the row for #{N}, implement end-to-end, add tests, verify analyze/test/build.
Do not commit unless I ask.
```

### 5.11 Source loading — make waiting feel alive (slow connectors)

> When `GET /sources/{id}/browse` takes 5–15s (connector retries, CF, etc.), the
> Sources grid sits on skeletons and feels broken/boring. **UI-only** — do not fix
> connectors; make the wait delightful.

```
ManhwaManiacs — source loading delight. Connectors FROZEN (no backend/connectors/).

## Problem

Source browse can take a long time. Static skeleton grids feel dead. User wants
waiting to feel intentional and interesting, not like the app is stuck.

## Ideas to implement (pick achievable set)

**★ User-preferred solution (prioritize this):**

0. **Animated "Latest reads" carousel while loading** — When a source browse request
   is slow, show the user's **recently read series** (from library continue-reading /
   reading history API — already authenticated) as a **non-interactive** animated
   showcase until the catalog loads:
   - Display **3 covers at a time** (horizontal row or gentle carousel)
   - Auto-rotate / cross-fade to the next 3 every ~3–4s (infinite loop)
   - Covers are **not clickable** — decorative entertainment only; optional subtle
     parallax or scale breathe; reuse ScrollReveal / shimmer motion language
   - Headline: e.g. "Your latest reads while we open {SourceName}…"
   - Keep the branded source loader above or below (logo + "Opening…")
   - **Stop immediately** when browse data arrives; cross-fade into real catalog
   - Graceful fallback: if no history yet, fall back to tips (#3) or skeleton (#2)

1. **Branded loading stage** — source logo + name front and center; subtle breathe
   animation on the favicon; "Opening {Toonily}…" copy.

2. **Progressive reveal skeleton** — shimmer cards stagger in (reuse ScrollReveal /
   shimmer patterns); count ticks up ("Loading catalog…").

3. **Rotating tips** — calm reading tips / feature hints cycle every 4s while loading:
   "Double-tap the reader to zoom", "Pin sources from the ⋮ menu", etc.

4. **Stale-while-revalidate** — if we have cached browse from last visit (localStorage /
   mobile prefs), show faded previous catalog immediately with "Refreshing…" banner.

5. **Honest slow-load messaging** — after 3s: "This source is waking up — can take
   ~10s"; after 10s: "Still trying…" with retry button (no new connector logic).

6. **Ambient source tint** — very muted background wash from source brand color (like
   profile moods — not bright).

7. **Mini activity feed** — while waiting, show "Readers often pick…" top 3 from
   *cached* global stats or last-known browse (graceful empty state).

8. **Custom loader** — corner page-flip or ink-drop animation (on-brand manga motif),
   not CircularProgressIndicator alone.

9. **Sound/haptic optional** — subtle haptic when catalog finally lands (mobile);
   respect hapticFeedback setting.

10. **Error as personality** — on 502/timeout, friendly copy + "Try again" + suggest
    pin a faster source; never raw stack traces.

## Surfaces

- Web: `frontend/src/features/sources/` browse grid + SourceSeriesGrid
- Mobile: `source_browser_screen.dart`, `sources_list_screen.dart`
- Data: `GET /library/continue-reading` or reading history — do not wait on slow source

## UX rules for #0 (latest reads carousel)

- Never fake click affordance (no Pressable, no hover pointer, no navigation)
- Respect `prefers-reduced-motion`: static grid of 3, no rotation
- Do not block or delay the real catalog request — carousel is overlay/inline state only
- Loop until `browse` resolves (success or error)

## Verify

cd frontend && npm run typecheck && npm run test
cd mobile && flutter analyze lib && flutter test

Do NOT touch backend/connectors/.
Do not commit unless I ask.
```

### 5.12 Wave 2 — parallel multi-agent orchestration (paste coordinator + spawn agents)

> **P1 is done.** Run Wave 2 next. Fix lint first (Agent 0, ~15 min) — it blocks CI
> and touches `SourceBrowserView` where the loading carousel will live anyway.

#### Coordinator prompt (paste once, you orchestrate)

```
You are the Wave 2 coordinator for ManhwaManiacs at /home/yash/dev/aistudio (develop).

P1 Integration Polish is COMPLETE (UpdateBanner, OCR UI, updates 409 verified).
Connectors FROZEN — no backend/connectors/ edits.

Spawn these agents IN PARALLEL (separate chats / subagents). Each agent owns
disjoint file paths — no two agents edit the same file.

| Agent | Owns | Blocked by |
|-------|------|------------|
| 0 Lint | frontend SourceBrowserView + VirtualPageList lint only | nothing |
| A Backend Profiles | backend routes/models for reading_profiles | nothing |
| B Web Profiles | frontend/src/features/profiles/** | A for API wire (can stub first) |
| C Mobile Profiles | mobile/lib/features/profiles/** | A for API wire (can stub first) |
| D Web Reader | frontend reader seamless pages §5.9 | nothing |
| E Mobile Reader | mobile reader seamless pages §5.9 | nothing |
| F Web Source Load | frontend source loading carousel §5.11 | 0 (same SourceBrowserView) |
| G Mobile Source Load | mobile source loading carousel §5.11 | nothing |
| H Backend Perf | download re-index O(n²) fix | nothing |

Merge order: 0 → (A parallel with D,E,G,H) → (B,C after A or with stubs) → F last
(F touches SourceBrowserView after Agent 0).

Each agent: do not commit. Report files changed + verify commands run.

When all green: user decides deploy/commit.
```

#### Agent 0 — Lint unblock (run FIRST, solo, ~15 min)

```
ManhwaManiacs Agent 0 — CI lint unblock only.

Fix frontend lint to 0 errors:
- frontend/src/features/sources/components/SourceBrowserView.tsx — setState in effect (derive genre from props or key remount, no sync setState in useEffect)
- frontend/src/features/reader/components/VirtualPageList.tsx — react-hooks/incompatible-library on useVirtualizer (eslint-disable-next-line with comment, or restructure per TanStack docs)

Also fix warnings in SourceBrowserView if trivial.

ONLY touch those two files. No feature work.

Verify: cd frontend && npm run lint && npm run typecheck && npm run test
Connectors FROZEN. Do not commit unless I ask.
```

#### Agent A — Backend reading profiles API

```
ManhwaManiacs Agent A — backend reading profiles (Phase 4 slice).

Connectors FROZEN. Read docs/CLAUDE_HANDOFF.md §5.8.

Deliver:
1. Alembic migration: reading_profiles table (user_id FK, name, avatar_key, mood enum, sort_order, created_at)
2. CRUD routes: GET/POST/PATCH/DELETE /profiles (scoped to session user)
3. Active profile: X-Profile-Id header accepted on library/reader routes (store in request context; v1 can be no-op on data scoping if too large — but header must not 400)
4. pytest: test_profiles.py — create, list, update, delete, auth gate

Do NOT touch backend/connectors/.
Verify: cd backend && python -m pytest tests/test_profiles.py tests/test_auth.py -q
Do not commit unless I ask.
```

#### Agent B — Web Netflix profiles UI

```
ManhwaManiacs Agent B — web profiles UI only.

Connectors FROZEN. Read docs/CLAUDE_HANDOFF.md §5.8.

Own ONLY: frontend/src/features/profiles/**, frontend/src/app/profiles/**, app-shell redirect gate, nav if needed.

Deliver:
- Profile picker after auth (before home): "What are you going to read today?"
- Add profile, staggered animations, mood → muted background tint
- Stay signed in — never re-prompt login if mm_session valid
- Wire to GET/POST /profiles (if API not ready, stub types matching Agent A contract)
- Settings → manage profiles + profile handoff (§5.10 #16)

Do NOT edit mobile/, backend/connectors/, or SourceBrowserView.

Verify: cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
Do not commit unless I ask.
```

#### Agent C — Mobile Netflix profiles UI

```
ManhwaManiacs Agent C — mobile profiles UI only.

Connectors FROZEN. Read docs/CLAUDE_HANDOFF.md §5.8.

Own ONLY: mobile/lib/features/profiles/**, app_router.dart redirect gate.

Same UX as web Agent B: picker, add, mood themes, animations, persistent login.
Reuse ScrollReveal motion language.

Do NOT edit frontend/, backend/, or reader_content.dart.

Verify: cd mobile && flutter analyze lib && flutter test
Do not commit unless I ask.
```

#### Agent D — Web reader seamless pages

```
ManhwaManiacs Agent D — web reader seamless pages §5.9.

Own ONLY: frontend/src/features/reader/** (VirtualPageList, PageImage, page-layout).

Remove black gaps/lines between vertical pages:
- Remove pb-1 inter-page gap default OFF
- Optional Settings toggle for thin gap
- Fix virtualizer height drift if gaps persist

Do NOT edit mobile/ or SourceBrowserView.

Verify: cd frontend && npm run typecheck && npm run lint && npm run test
Do not commit unless I ask.
```

#### Agent E — Mobile reader seamless pages

```
ManhwaManiacs Agent E — mobile reader seamless pages §5.9.

Own ONLY: mobile/lib/features/reader/** (reader_content.dart, reader_page_image.dart).

Remove AppSpacing.xs padding between vertical pages (default flush stack).
Optional reader setting for page gap.

Do NOT edit frontend/ or profiles/.

Verify: cd mobile && flutter analyze lib && flutter test
Do not commit unless I ask.
```

#### Agent F — Web source loading carousel (run AFTER Agent 0)

```
ManhwaManiacs Agent F — web source loading delight §5.11.

Connectors FROZEN. Agent 0 lint must be merged first (SourceBrowserView).

Own ONLY: frontend/src/features/sources/** (browse loading state).

★ User solution: while browse is slow, show animated "Latest reads" carousel:
- 3 covers at a time from GET /library/continue-reading (or history)
- Auto-rotate every 3–4s, NOT clickable, loops until browse resolves
- Cross-fade to real catalog on success
- Fallback: tips or skeleton if no history
- Branded "Opening {source}…" above carousel

Verify: cd frontend && npm run typecheck && npm run lint && npm run test
Do not commit unless I ask.
```

#### Agent G — Mobile source loading carousel

```
ManhwaManiacs Agent G — mobile source loading delight §5.11.

Connectors FROZEN. Own ONLY: mobile source_browser_screen.dart + new widget in features/sources/widgets/.

Same carousel as Agent F: 3 latest reads, rotate, non-interactive, until browse loads.
Use continue-reading API. Haptic optional when catalog lands.

Verify: cd mobile && flutter analyze lib && flutter test
Do not commit unless I ask.
```

#### Agent H — Backend download re-index perf

```
ManhwaManiacs Agent H — download O(n²) re-index fix.

Own ONLY: backend/services/download_manager.py + tests.

Fix ~line 650: incremental index on chapter completion, not full library rescan.
Add/adjust pytest.

Do NOT touch backend/connectors/.

Verify: cd backend && python -m pytest tests/ -q -k download
Do not commit unless I ask.
```

### 5.13 app.manhwamaniacs.xyz — APK download subdomain

> **Goal:** Open **https://app.manhwamaniacs.xyz** on your phone → pretty install
> page → tap Download → get the latest APK. Runs on the NAS via Caddy + deploy.sh.

```
================================================================================
MANHWAMANIACS — app.manhwamaniacs.xyz APK SUBDOMAIN (full prompt)
Repo: /home/yash/dev/aistudio | Branch: develop
Connectors FROZEN. Do not commit unless user asks.
================================================================================

## Objective

Dedicated subdomain **app.manhwamaniacs.xyz** (production) for the Android app:
- Phone browser opens a polished install landing page
- One-tap APK download (latest flutter build)
- Works on the NAS deploy stack (ops/deploy.sh + Caddy + Docker)

Today: /app/* routes exist on the backend (app_distribution.py) but APK path
points at REPO_ROOT/mobile/build/... which does NOT exist inside the backend
Docker container. Deploy does not build or ship the APK.

## Deliverables

### 1. Fix APK serving in Docker

- Add env `MM_APK_PATH` (default `/app/apk/app-release.apk` in container)
- Update backend/core/config.py + app_distribution.py to use it
- docker-compose.yml: mount host APK into backend:
  `./apk/app-release.apk:/app/apk/app-release.apk:ro` (path relative to deploy dir)
- If APK missing: landing page shows friendly "not built yet" (already partially there); /app/download 404 with clear message

### 2. Build APK during deploy

Update ops/deploy.sh `do_deploy()` after rsync:
- If `flutter` is on PATH, run:
  `cd "$DIR/mobile" && flutter pub get && flutter build apk --release --dart-define=FLAVOR=prod`
- Copy output to `$DIR/apk/app-release.apk` (mkdir -p)
- If flutter missing: warn in deploy log, skip (don't fail deploy) — page shows build instructions
- Optionally bump mobile/pubspec.yaml build number in deploy (document only; don't auto-bump unless easy)

### 3. Caddy vhost app.manhwamaniacs.xyz

In ops/deploy.sh, for **production** only, write an extra vhost
`/srv/caddy/conf.d/manhwamaniacs-production-app.caddy`:

```
app.manhwamaniacs.xyz {
    tls internal
    import sec
    import zip
    import logroll manhwamaniacs-production-app
    reverse_proxy manhwamaniacs-production-backend:8000
}
```

Requirements:
- Backend container must be reachable from Caddy on port 8000. Add backend to the
  `edge` Docker network (keep it off host ports — only Caddy talks to it).
- Do NOT expose backend on manhwamaniacs.xyz apex (frontend stays the only apex target).
- reload_caddy after write (same as main vhost)
- destroy-preview / rollback should not leave orphan app vhost broken

Optional: `app.staging.manhwamaniacs.xyz` for staging — same pattern if easy.

### 4. Landing page URLs

Backend system.py already serves HTML at `/` when Accept: text/html.
Ensure app.manhwamaniacs.xyz/ shows the existing render_landing_html() page with:
- Download button → `/app/download` (same origin, no /api prefix needed on app subdomain)
- Version from pubspec
- Server status probe → `/health` (not /api/health on this host)

Update inline JS in app_distribution.py if it hardcodes `/api/` paths — use relative URLs.

### 5. DNS / docs (manual step — document clearly)

Add to docs/DEPLOY.md or mobile/RELEASE.md:
- Cloudflare DNS: CNAME `app` → same tunnel target as manhwamaniacs.xyz
- Or add `app.manhwamaniacs.xyz` to Cloudflare Tunnel public hostnames → Caddy :443
- Verify: `curl -sk https://app.manhwamaniacs.xyz/health`

### 6. Homepage + mobile hints

- ops/deploy.sh homepage_sync: add "Android app" link → https://app.manhwamaniacs.xyz
- mobile setup screen / app update provider: document that APK lives at
  https://app.manhwamaniacs.xyz/app/download (optional default hint text)

### 7. Tests

- backend pytest: app_download 404 when APK missing, 200 when temp file present
- Smoke test path in test or deploy.sh comment

## Files likely touched

- backend/core/config.py
- backend/routes/app_distribution.py
- backend/tests/test_app_distribution.py (new or extend)
- docker-compose.yml (backend edge network + apk volume)
- ops/deploy.sh (flutter build, apk copy, app vhost)
- docs/DEPLOY.md or mobile/RELEASE.md
- Maybe backend/Dockerfile (mkdir /app/apk)

## Verify

cd backend && python -m pytest tests/ -q -k app
cd frontend && npm run typecheck   # if any frontend hint changed
# After deploy (user runs): ops/deploy.sh production
# Phone: open https://app.manhwamaniacs.xyz → download APK

## Do NOT

- Touch backend/connectors/
- Break existing manhwamaniacs.xyz apex (web app unchanged)
- Commit unless user asks

## Report when done

- Exact URL to open on phone
- Cloudflare/DNS steps user must do manually (if any)
- Whether flutter build ran on deploy or needs manual build
- Screenshot description of landing page
```

### 5.14 Go-live — fix app white screen + deploy everything (NAS)

> **User symptom:** https://app.manhwamaniacs.xyz shows blank white page (HTTP 200,
> 0 bytes). DNS CNAME is done. Code committed (ef6f522 app subdomain) but
> `sudo ops/deploy.sh production` was NOT run successfully (permission denied without root).
> No `manhwamaniacs-production-app.caddy` on disk yet.

```
================================================================================
MANHWAMANIACS — GO-LIVE: DEPLOY EVERYTHING ON NAS (single agent, do it all)
Repo: /home/yash/dev/aistudio | Branch: develop
NAS paths: /srv/caddy, /srv/apps/manhwamaniacs, ops/deploy.sh
Connectors FROZEN for new code — but deploy will ship existing working-tree connectors.
================================================================================

## Your job

Fix the white screen and get production fully live. Do NOT ask the user to run
commands — YOU run everything you can on the NAS. Only ask user if sudo password
is required and you cannot proceed.

## Known state

- ef6f522 committed: app subdomain code (app_distribution, docker-compose, deploy.sh, RELEASE.md)
- ~112 uncommitted files in working tree: Wave 2 (profiles, reader, carousel) + connector WIP
- DNS: app CNAME → Cloudflare tunnel (user already added)
- app.manhwamaniacs.xyz returns 200 with EMPTY body — no Caddy app vhost deployed
- manhwamaniacs.xyz main site API health works
- Deploy WITHOUT sudo fails: Permission denied on /srv/caddy and /srv/apps

## Steps (execute in order)

### 1. Preflight
- cd /home/yash/dev/aistudio
- git status, git log -3 --oneline
- Confirm manhwamaniacs-production-app.caddy missing: ls /srv/caddy/conf.d/
- curl -sk https://app.manhwamaniacs.xyz/health (expect empty or broken)
- curl -sk https://manhwamaniacs.xyz/api/health (expect JSON)

### 2. Production deploy (MUST use sudo)
sudo ops/deploy.sh production

If sudo needs password and blocks you: document exact blocker for user.

Deploy should:
- rsync working tree → /srv/apps/manhwamaniacs/production/
- build_apk() → /srv/apps/manhwamaniacs/production/apk/app-release.apk
- docker compose build + up (backend on edge network + apk mount)
- write /srv/caddy/conf.d/manhwamaniacs-production-app.caddy
- reload Caddy
- health gate pass

If deploy fails:
- Read logs: docker logs manhwamaniacs-production, manhwamaniacs-production-backend
- Fix deploy script or compose ONLY if clear bug (minimal diff)
- Retry sudo ops/deploy.sh production
- Do NOT leave production in rolled-back broken state if fixable

### 3. Verify app subdomain (must pass before done)
curl -sk https://app.manhwamaniacs.xyz/health
  → JSON {"status":"online",...} NOT empty

curl -sk -H "Accept: text/html" https://app.manhwamaniacs.xyz/ | head -20
  → HTML install landing page NOT empty

curl -skI https://app.manhwamaniacs.xyz/app/download
  → HTTP 200, content-type application/vnd.android.package-archive, size ~60MB

### 4. Verify main site
curl -sk https://manhwamaniacs.xyz/api/health → 200 JSON
Open/check frontend not white screen — if white:
- docker logs manhwamaniacs-production --tail 100
- fix JS crash / profile gate loop if found (Wave 2 in tree)
- rebuild frontend if needed

### 5. Database migration (profiles table if Wave 2 deployed)
If backend has reading_profiles migration and deploy is new:
- docker exec manhwamaniacs-production-backend alembic upgrade head
  OR confirm boot migration ran
- curl -sk -H "Cookie: ..." https://manhwamaniacs.xyz/api/profiles (with test session if possible)

### 6. Optional commit (only if user asked — default: do NOT commit)
Unless user explicitly asked to commit in this session: leave git as-is.

### 7. Report to user (plain English)

| Check | URL | Result |
|-------|-----|--------|
| App install page | https://app.manhwamaniacs.xyz | |
| APK download | https://app.manhwamaniacs.xyz/app/download | |
| Main web | https://manhwamaniacs.xyz | |
| Phone steps | open app URL → Download → install | |

Include: APK version, file size, any caveats (uncommitted tree deployed).

## Do NOT
- Add new features
- Touch backend/connectors/ unless deploy is blocked and fix is unrelated
- Force-push main

## Success criteria
User can open https://app.manhwamaniacs.xyz on phone and see install page + download APK.
```

### 5.15 Series page UX + persistent mood shell + download-while-reading (#13)

> **User request (web + mobile parity).** Screenshot: source series detail (DEBTBOUND BY BLOOD).

```
================================================================================
MANHWAMANIACS — SERIES DETAIL UX + MOOD SHELL + DOWNLOAD-WHILE-READING
Repo: /home/yash/dev/aistudio | Branch: develop
Connectors FROZEN. Web + mobile parity. Do not commit unless user asks.
================================================================================

## 1. Download while reading (#13 from polish backlog)

When user reads an **online source chapter** (source reader):
- On Wi-Fi only (respect existing download Wi-Fi guard on mobile; mirror on web if setting exists)
- Auto-queue the **next 2 chapters** of the same series in background
- No toast spam — quiet queue; optional subtle "Queued next chapters" once
- Skip if already downloaded/queued
- Files: frontend source reader hooks, mobile source_reader_provider / downloads

## 2. Source series — chapter list sorting

**Default: newest first** (Ch 33, 32, 31 …) — descending by chapter number.

Add sort control in Chapters header:
- Newest first (default)
- Oldest first
- Persist preference per-series in localStorage / shared prefs (optional)

Web: frontend/src/features/sources/components/SourceSeriesDetailView.tsx
Mobile: mobile/lib/features/sources/screens/source_series_detail_screen.dart

Sort after fetch; handle decimal chapters (1.5, 2, etc.) numerically.

## 3. Read chapters look darker

Chapter rows with saved progress:
- **Completed** (100% or last page): darker/muted row bg, slightly dimmed title (e.g. opacity 70%)
- **In progress**: normal brightness + progress text (below)
- **Unread**: current default styling

Use existing reading progress API for online source chapters (POST/GET reader progress
with source chapter ids — see reader remote mode). If progress not wired for sources yet,
wire it as part of this task (backend may already support via reader routes).

## 4. "Continue" instead of "Read Online"

Top CTA on series detail:
- **No progress** → "Read Online" → first chapter (or oldest if sort is oldest-first for read order — use **continue chapter** logic, not list sort)
- **Has progress** → **"Continue"** → exact chapter + page user left off
- Show subtitle: "Chapter 12 · page 14" under button if helpful

Continue target = latest in-progress or last-read chapter for this source+series+profile.

## 5. Chapter row progress: "14/25 pages" not just "27 pages"

Per chapter row:
- Unread: `27 pages`
- In progress: `14/27 pages` (current page / total)
- Complete: `27/27 pages` or checkmark + darker row

## 6. Netflix full-screen animations

Profile picker → app entry (and profile switch):
- **Full viewport** animation (100dvh/100vw), not a small card animation
- Selected profile scales, others blur/dim, mood tint **fills entire screen**
- 400–500ms cross-fade into shell (easeOutCubic)
- Profile switch from chip: same full-screen brief transition (can be shorter 250ms)
- Respect prefers-reduced-motion

Web: frontend/src/features/profiles/components/profile-picker.tsx
Mobile: mobile/lib/features/profiles/screens/profile_picker_screen.dart

## 7. Mood background on ENTIRE app (persistent)

**Problem:** User sees mood tint only on profile picker; in app the dark sidebar
(`bg-sidebar`) hides the tint — looks like it "disappears."

**Fix:**
- Mood gradient must cover **full shell**: sidebar, topbar, main content area
- Sidebar/topbar: use **semi-transparent** or mood-derived `bg-sidebar/80` so tint shows through
- `moodShellBackground(activeProfile.mood)` on outermost shell — already in app-shell.tsx;
  extend to sidebar.tsx, topbar.tsx (remove opaque overrides OR use mood-aware tokens)
- Tint persists for whole session until profile switch — NOT only on picker
- Reader stays pure obsidian (unchanged)
- Mobile: same — scaffold background + bottom nav use ProfileMoodTheme

Shared tokens: frontend features/profiles/mood.ts, mobile ProfileMoodTheme

## Verify

cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
cd mobile && flutter analyze lib && flutter test
cd backend && python -m pytest tests/ -q -k "progress or reader"  # if backend touched

## Files likely touched

- SourceSeriesDetailView.tsx, source_series_detail_screen.dart
- source reader progress hooks (web + mobile)
- app-shell.tsx, sidebar.tsx, topbar.tsx
- profile-picker.tsx, profile_picker_screen.dart
- downloads queue (wifi-guarded auto-queue)

## Success criteria (user-visible)

1. Open source series → chapters show 33, 32, 31… with sort toggle
2. Read ch 1 → row becomes darker; shows 27/27 when done
3. Leave ch 2 at page 14 → row shows 14/27; top button says **Continue**
4. Reading ch 2 on Wi-Fi → next 2 chapters queue quietly
5. Pick romantic profile → **whole app** (sidebar included) has soft rose tint all session
6. Profile pick feels Netflix full-screen, not a small popup
```

---

## 6. Verification commands (non-connector)

```bash
# Backend
cd backend && python -m pytest tests/ -q

# Frontend
cd frontend && npm run typecheck && npm run lint && npm run test && npm run build

# Mobile (if touched)
cd mobile && flutter analyze && flutter test
```

Production deploy (only if user asks):

```bash
cd /home/yash/dev/aistudio
docker compose -p manhwamaniacs-production build backend frontend
docker compose -p manhwamaniacs-production up -d backend frontend
```

---

## 7. When user says "fix sources"

Reply: *Source connectors are handled by Cursor in a separate rollout. I can help with UI around Sources (grid, reader, downloads) but not `backend/connectors/`. Should I work on integration polish or Phase 4 instead?*

---

*Last updated: 2026-07-12 — §5.14 deploy + app subdomain go-live prompt.*
