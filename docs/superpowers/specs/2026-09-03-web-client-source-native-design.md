# Web client: source-native migration + reader experience

**Date:** 2026-09-03
**Status:** Design — approved, not yet planned
**Sub-project:** 1b of 3. Depends on 1a (backend source-native rebuild, landed on `feat/vps-slim-source-native`). Sibling: 1c (mobile + deploy).
**Branch:** same `feat/vps-slim-source-native` — not merged to `main` until 1a+1b+1c all land.

---

## 1. Why

1a rewrote the backend around `(source_id, series_key, chapter_key)` identity, deleted the
server-side download engine, and merged the progress/library tables. Every web API call now
targets a shape that no longer exists. This sub-project migrates the Next.js client to the new
API **and**, because the reader is being rewritten anyway, makes the viewing experience the
best it can be (owner's explicit priority).

### Ratified decisions (brainstorming 2026-09-03)

| Decision | Value |
|---|---|
| Web OCR | **Search-only.** Web queries the global `chapter_ocr` store and renders text in the reader; it does **not** run OCR. Mobile (1c) populates the store. |
| Reader polish | **In scope for 1b.** Seamless pages, cinema mode, continue-hero, seamless chapter transitions, mood tint in the reader — all here, not deferred. |
| Nav | Drop the server "Downloads" section. Rename "Offline" → **"Downloads"** (device-saved chapters are now *the* download). |
| Offline SW architecture | **Kept.** The service-worker system (`public/sw.js`, `features/offline/`) is well-built and tested — repoint its URLs, don't rewrite it. |

---

## 2. Identity & API surface

Client mirrors 1a: a series is `(sourceId, seriesKey)`, a chapter is
`(sourceId, seriesKey, chapterKey)`. Keys are opaque strings — **URL-encode with
`encodeURIComponent` at every call site**, never concatenate raw (they contain `/`).

`src/services/http.ts` — **almost no change**: it already sends `credentials: "include"`
(the `mm_session` cookie) and `X-Profile-Id` from the profile store on every call. Add:
one helper `sourceChapterQuery({sourceId, seriesKey, chapterKey})` → `{source, series, chapter}`
query object, used everywhere.

### Endpoint remap (every `features/*/api.ts`)

| Old | New |
|---|---|
| `GET /library/series/{id}` (int) | `GET /library/series/{followed_id}` **or** `GET /library/series?source=&series=` for a not-yet-followed source series (detail = cache meta + live chapters + progress overlay) |
| `POST /library/series/{id}/add` | `POST /library/follow` `{source_id, series_key}` |
| `DELETE /library/series/{id}` | `DELETE /library/follow/{followed_id}` |
| `PATCH /library/series/{id}` | `PATCH /library/series/{followed_id}` (favorite / reading_status / notify) |
| `GET /library/covers/{id}` (int) | `GET /sources/{source}/series/{series:path}/cover` |
| `GET /reader/chapter/{id}` (int) | `GET /reader/chapter/manifest?source=&series=&chapter=` |
| `GET /reader/page/{id}/image` (int) | `GET /sources/{source}/pages/{page:path}/image` (URL from the manifest) |
| `POST /reader/progress` `{series_id, chapter_id, last_page}` (int) | `POST /reader/progress` `{source_id, series_key, chapter_key, chapter_number, last_page, page_count, scroll_offset_px, is_completed}` |
| — | `POST /reader/progress/batch` (offline-sync flush) |
| `GET /reader/bookmarks`, `POST /reader/bookmark` | source-native bodies |
| `GET /downloads`, `POST /downloads/*`, `PUT /downloads/settings` | **removed** |
| `POST /library/import`, `GET /library/scan-status`, `GET /library/libraries` | **removed** |
| `GET /updates/notifications` etc. | source-native; note `/updates/settings` is **GET/PUT** (not PATCH); notification routes: `PATCH /updates/notifications/{id}/read`, `POST /updates/notifications/read-all`, `GET /updates/notifications/unread-count` |
| `GET /ocr/search?q=` | unchanged path, source-native result rows; **no** `/ocr/queue|jobs|metrics` |

### `src/types/`

Rewrite `api.ts`, `library.ts`, `reader/types.ts`, `downloads/types.ts` (delete), etc. The
domain identity everywhere becomes `{ sourceId: string; seriesKey: string; chapterKey?: string }`.
`ReaderChapterContent.mode` (`"local" | "remote"`) is **deleted** — there is only source content.

---

## 3. Feature-by-feature

### 3.1 `features/downloads/` → **deleted**
Delete the directory (`api.ts`, `hooks.ts`, `grouping.ts` + test, `types.ts`,
`DownloadsView.tsx` 1117 L, `DownloadSettingsPanel.tsx`). Delete `src/app/downloads/`.
Remove `Download` from `nav.ts` `primaryNav` and `mobileNav`. Remove the download-settings
block from `src/app/settings` + `features/preferences`.

### 3.2 `features/offline/` → renamed **Downloads**, repointed
Architecture unchanged (SW is the sole Cache Storage writer, per-profile scoped cache names,
retention/sweep/read-then-expire all stay). Changes:
- `save-request.ts` `buildSaveRequest`: `payloadUrl` `/reader/chapter/{id}` →
  `/reader/chapter/manifest?source=&series=&chapter=`; `imageUrls` come from the manifest's
  `pages[].url` (already absolute source-proxy URLs); `key` becomes
  `${sourceId}:${seriesKey}:${chapterKey}`.
- `protocol.ts` `SaveChapterRequest`: `chapterId`/`seriesId` → `sourceId`/`seriesKey`/`chapterKey`;
  `documentUrl` points at the new unified reader route.
- `client.ts` `resolveApiBase` unchanged.
- User-facing strings: "Offline" → "Downloads"; `OfflineLibraryView` → `DownloadsView`,
  `OfflineChapterControl` → `DownloadChapterControl`. Route `/offline` → `/downloads`
  (reuse the freed path). Nav: `moreNav` "Downloads" (icon `Download`), remove old `/offline`.
- `sw.js` / `sw-policy.js`: update the API-URL matcher for the manifest + source-image shapes;
  the cache-key derivation stays scope-first. Bump the SW version constant so clients update.
- Tests: `sw-integration.test.ts`, `policy-contract.test.ts`, `verify-isolation.test.ts`,
  `save-request.test.ts` — rewrite fixtures to source-native URLs; keep the isolation assertions.

### 3.3 `features/reader/` → one source-native reader + full polish

**Route consolidation.** `src/app/reader/[seriesId]/` (local) and `src/app/reader/online/`
collapse into **`src/app/reader/[sourceId]/[seriesKey]/[chapterKey]/`** (all URL-encoded
segments). `SourceReader.tsx` and the local `ChapterReader` local-mode branches merge —
`ChapterReader` becomes source-only. `reader/api.ts`: delete `toReaderChapterContent` (local),
`readerPageImageUrl(pageId: number)`; `toRemoteReaderChapterContent` → the sole
`manifestToChapterContent(manifest)`.

**Content source per state:**
- online: pages stream from `/sources/{source}/pages/{page}/image` (backend proxy, no server cache)
- downloaded: the SW serves the same URLs from Cache Storage — the reader is unaware which

**Preferences** (`preferences.ts`) unchanged in shape (per-series `readingMode` /
`fitMode` / `direction` / `zoom`), rekeyed `${sourceId}:${seriesKey}`.

**Viewing-experience work (all in 1b):**

1. **Seamless pages.** `VirtualPageList` — remove the `pb-1` inter-page gap; pages stack
   flush edge-to-edge in continuous mode. Letterboxing (aspect gaps) filled with the reader
   backdrop colour, never black. New `Settings → Reader → Page gap` toggle, default **off**.
   Fix `estimateSize` vs measured-height drift so scrolling never reveals a seam or "hits air".
2. **Fast open.** Render the reader shell + first page from the manifest immediately; for a
   downloaded chapter the SW answers from cache so first paint is near-instant. Preload
   (`preload.ts`, `use-chapter-preload.ts`) tuned: next N pages of the current chapter + page 1
   of the next chapter always in flight.
3. **Cinema mode.** A toggle (and auto after ~3 s idle) that hides *all* chrome —
   top bar, scrub bar, page counter. Counter + controls fade back in on tap / pointer-move /
   pause. `prefers-reduced-motion` → instant, no fade. Persisted per-profile.
4. **Seamless chapter transition.** At end-of-chapter in continuous mode, an end-card slides
   up ("Next: Ch N") with the next chapter **already prefetched**; a tap or continued scroll
   drops straight into it with no route flash (client-side swap, URL updated via `history`).
5. **Continue-hero.** `ContinueReading` on the library landing gains a lead **hero card** —
   large cover, series + "Ch N · page P", one tap resumes the exact page. The existing
   horizontal rail follows it for the rest. Source-native rekey (`item.source_id` +
   `series_key` + `chapter_key`), cover via the source proxy.
6. **Ambient mood tint in the reader.** The profile mood system (`profiles/mood.ts`:
   `moodShellBackground`, `MOOD_TINT`, `isTintedMood`) already tints the shell. Extend a
   *very* subtle wash into the reader's side margins only (never behind the page). Reader page
   background stays pure obsidian. Off for `mood: "default"`.
7. **Read-state on the chapter list.** In `SeriesDetailView`, completed chapters render
   dimmed/darker, in-progress show `14/27 pages`, unread normal — from `chapter_progress`.
   Top CTA: "Continue" (→ exact chapter+page) when progress exists, else "Read".
8. **Chapter list sort.** Default newest-first; a sort control (newest / oldest), persisted
   per series in scoped localStorage. Decimal chapters sort numerically.

**Keep working:** keyboard shortcuts (`keymap.ts`, `use-reader-shortcuts.ts`), scrub bar,
spread/double-page logic, fit/zoom, RTL, `ShortcutsOverlay`.

### 3.4 `features/library/`
- `SeriesFollowButton` + `LibraryMembershipButton` → one `FollowButton` (follow/unfollow a
  `(source, series_key)`).
- `SeriesCard` / `SeriesGrid` / `LibraryShelfView` / `LibraryView` / `LibraryToolbar` —
  `followed_series` list shape; filters `status` / `favorite` / `reading_status` / `search` /
  `sort`; cover via source proxy. Drop `library_id`, `has_chapters`, `language` filters that
  1a removed.
- `SeriesDetailView` (567 L) — cache meta + live chapter list + progress overlay; the read-state
  + sort + CTA work from §3.3.7–8 lands here.
- `StatisticsView` / `ReadingHistoryView` / `RecommendationsView` / `CollectionsView` /
  `CollectionDetailView` / `BookmarksView` — source-native rekey. `DuplicateNotice` /
  `BulkActionBar` — revisit against the followed model.
- `SearchView` — `GET /library/search` over the followed set + federated `GET /sources/search`;
  drop the local-catalog branch.
- Delete `ImportResponse`, `ScanStatus`, import UI, `/library/browse` "libraries" concept
  (keep `/library/browse` as the federated-catalogue entry).

### 3.5 `features/ocr/` — search-only
`OcrSearchView`: `GET /ocr/search?q=` → source-native rows (series title, chapter, snippet
with `<mark>`, link into the reader at that page). Delete any queue/job/metrics UI and the
"run OCR" affordance. In the reader, `GET /ocr/chapter?source=&series=&chapter=` provides
`page_texts` for tap-to-reveal dialogue (read-only; absent = feature quietly off for that
chapter).

### 3.6 `features/updates/`
Source-native notification list + `SeriesTracker`→`followed_series` shapes. `UpdateBanner`,
`NotificationsView`, settings panel (`GET/PUT /updates/settings`, no `auto_download`).
"New chapter" → deep-links into the reader.

### 3.7 `features/profiles/`, `preferences/`, `search/`, `admin/`
Profiles: `mature_content_enabled` is now settable at create/edit (1a added it) — add the
toggle to the create/edit form. Preferences: drop download-settings; keep reader gap toggle,
cinema default, mature gate. Search: as §3.4. Admin `/admin/status`: drop download-worker /
OCR-worker widgets; keep source health + update runs.

### 3.8 Nav (`src/config/nav.ts`)
```
primaryNav:  Library · Browse all · Sources · Updates · Search          (Downloads removed)
moreNav:     Downloads (was Offline) · Collections · Recommendations ·
             Statistics · History · Bookmarks · OCR Search
mobileNav:   Library · Sources · Downloads · Search · More              (Downloads = device saves)
```

### 3.9 `next.config.ts`
`images.remotePatterns` currently only allows `127.0.0.1:8000` / `localhost:8000`. Add the
production origin and — because covers/pages proxy through the backend same-origin `/api` —
confirm `/api/**` same-origin images need no `remotePatterns` entry (they don't; only the
`next/image` optimizer path does, and most reader images use `unoptimized`). Audit every
`<Image>`: reader pages and covers stay `unoptimized` (they're already-sized JP/WebP from a
proxy). Keep the `/` → `/library` redirect and the SW cache headers.

---

## 4. Testing

- **vitest:** rewrite `features/*/api.test` fixtures to source-native; `reader/*` unit tests
  (`fit`, `spread`, `preferences`, `scroll-preparation`, `preload`, `keymap`) mostly survive
  a rekey; `offline/*` tests rewritten per §3.2.
- **New vitest:** `manifestToChapterContent` shape; seamless-page zero-gap layout math;
  cinema-mode chrome-visibility state machine; continue-hero rekey; mood-tint "default = none".
- **Playwright** (`playwright` is a dep; wire config + `e2e/`): login → pick profile →
  library loads → open a source series → follow → open reader → progress persists (reload) →
  save for offline → go offline (`context.setOffline`) → reopen chapter from cache → search OCR.
- `scripts/verify-reader.mjs` — update its localStorage keys / routes.
- Gates: `npm run typecheck && npm run lint && npm run test && npm run build`.

---

## 5. Rollout / sequencing

All on `feat/vps-slim-source-native`. Suggested internal order for the plan:
1. Types + `http.ts` helper + endpoint remap in every `api.ts` (compiles, nothing renders yet).
2. Delete `downloads/`; nav; settings prune.
3. Library feature to source-native (grid, detail, follow, search, collections, stats, history).
4. Reader: route consolidation + `manifestToChapterContent` + progress → **reader renders online**.
5. Offline SW repoint + rename → **downloaded chapters read offline**.
6. Reader polish §3.3.1–8.
7. OCR search-only, updates, profiles, admin.
8. Tests (vitest rewrite + Playwright) + `build` green.

Between 1 and 4 the app doesn't fully render — acceptable, nothing is deployed.

---

## 6. Open questions (resolve in planning)

- **O-1 — reader route shape.** `/reader/[sourceId]/[seriesKey]/[chapterKey]` with encoded
  segments vs. `/reader?source=&series=&chapter=` query form. Path form is prettier and
  shareable but Next.js dynamic segments + heavily-encoded keys (`%2F`) can be fragile.
  Lean: path form with `[...chapterKey]` catch-all for slashes. Decide with a spike.
- **O-2 — cover proxy & slashes.** `series_key` in the cover URL must be encoded the way
  1a's `browse_service` expects (`quote(safe="")`). 1a flagged the fallback URL in
  `followed_series_service` — coordinate.
- **O-3 — SW cache migration.** Existing users have chapters cached under old int-keyed URLs.
  On SW version bump, the old caches are orphaned. Acceptable (personal instance, small data)
  — the sweep can drop unrecognised cache entries, or just let the version bump clear them.
- **O-4 — continue-hero when nothing in progress.** Empty state: hide the hero, or show a
  "start something" prompt seeded from recommendations. Lean: hide (matches current rail).
- **O-5 — double-page + seamless chapter transition interaction.** End-card behaviour in
  paged/double mode vs continuous. v1: end-card only in continuous; paged shows a "next" arrow.
