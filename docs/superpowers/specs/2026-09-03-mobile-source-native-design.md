# Mobile client: source-native migration + on-device downloads (1c)

**Date:** 2026-09-03
**Status:** Design — operating mode is build-through (no review gate), user validates on the live app
**Sub-project:** 3 of 3. Depends on 1a (backend, done + deployed) and mirrors 1b (web, ~done).
**Branch:** `feat/vps-slim-source-native`.

---

## 1. Why

1a rewrote the backend around `(source_id, series_key, chapter_key)` and deleted the
server-side download engine. The Flutter app still speaks the old int-keyed API and treats
"download" as "the server fetches it". 1c makes the phone a first-class source-native client
and — the whole point of the pivot — gives it the **on-device chapter store** so downloaded
chapters read with no server and no internet. `docs/OFFLINE_READING.md` remains the deep
design reference for the store; this spec supersedes its NAS-primary framing (phone-only now).

### Fixed decisions

| Topic | Decision |
|---|---|
| API base | Unchanged: `--dart-define=API_URL=https://app.manhwamaniacs.xyz` (backend served directly on the app subdomain by the VPS Caddy). |
| Identity | `(sourceId, seriesKey, chapterKey)` opaque strings everywhere; `chapterNumber` (double) carried alongside. |
| Store | sqflite (already a resolved transitive pod — promoting to a direct dep changes zero native inputs) + content-addressed blob tree under `getApplicationSupportDirectory()`. Never `getTemporaryDirectory()`. Never encrypted with a keychain-held key (sideload keychain loss = data loss). |
| Downloads | **Foreground-only** (sideloaded iOS has no dependable background execution). Queue with resume, bounded retry, ~1.5 GB free-space floor. |
| Retention | Read-then-expire: finishing a chapter stamps `read_at`; sweep on launch/resume deletes phone blobs 48 h later. Pinned series exempt. Re-open clears the stamp. Progress rows survive deletion. |
| Progress sync | Local outbox; flush via `POST /reader/progress/batch`; merge is server-side furthest-wins. Never rewind on pull. |
| OCR | Client-driven, **zero new CocoaPods**: a `mm/ocr` MethodChannel — iOS implements it with the Vision framework in Swift inside the Runner target (no pod), Android with ML Kit via a Gradle dependency + Kotlin (no Flutter plugin). Extracted text uploads to `POST /ocr/chapter`. If a platform impl is missing, the feature is silently off. |
| iOS distribution | Existing GitHub Actions cloud-Mac workflow, retargeted to this branch; VPS fetches the IPA and serves `/app/source.json` for SideStore (replaces the NAS cron). Blocked on user for push auth + repo visibility/PAT. |
| Android distribution | APK built locally on the laptop (userspace JDK17 + Android SDK), copied to `/srv/manhwamaniacs/apk/` on the VPS; `app.manhwamaniacs.xyz` serves it. |

---

## 2. API remap (mirror of 1b §2)

Dio clients in each feature's `repository`/`api` layer move to:

| Old | New |
|---|---|
| `/library/series/{id}` int catalog | `GET /library/series` (followed list) / `GET /library/series/{followed_id}` |
| trackers (`/updates/trackers*`) | `POST /library/follow {source_id, series_key}` · `DELETE /library/follow/{id}` · `PATCH /library/series/{id}` |
| `/reader/chapter/{id}` + `/reader/page/{id}/image` | `GET /reader/chapter/manifest?source=&series=&chapter=` → `{page_count, chapter_number, pages:[{number,url}], prev, next}`; page bytes from `pages[].url` (source proxy) |
| int progress | `POST /reader/progress` (source-native body) · `POST /reader/progress/batch` · `GET /reader/progress/series` |
| `/downloads/*` (server queue) | **gone** — replaced by the on-device store |
| OCR queue/jobs | `POST /ocr/chapter` (ingest) · `GET /ocr/chapter` · `GET /ocr/search` · `GET /ocr/coverage` |
| updates | notifications list / unread-count / `{id}/read` / read-all; settings GET/**PUT** (no auto_download); runs; `POST /updates/check` |
| covers | `GET /sources/{source}/series/{series}/cover` |

Models: every feature model gains the string-triple identity; delete int-keyed ids and
`SourceChapterLink`-era types. Path keys are encoded per URL segment (mirror web's
`encodePathKey`: split on `/`, encode each, rejoin).

## 3. On-device store (`mobile/lib/features/downloads/` reborn)

Per OFFLINE_READING.md, condensed to what ships:

- **DB (sqflite):** tables `saved_chapters(scope_id, source_id, series_key, chapter_key, chapter_number, title, series_title, page_count, bytes, state, pinned, read_at, created_at)`, `saved_pages(scope_id, chapter_rowid, page_number, blob_hash, size)`, `blobs(hash, refcount, size)`, `progress_outbox(scope_id, payload_json, created_at)`. `scope_id = "u{userId}p{profileId}"` is the **leading column of every PK**; the store is constructed with its scope and providers return `null` without one — a profile can never see another's rows.
- **Blobs:** `Application Support/mm-store/blobs/{hash[0:2]}/{hash}` — content-addressed (sha256 of bytes), refcounted for cross-profile dedupe.
- **Queue engine:** fetch manifest → fetch pages sequentially (concurrency 2), hash + write blob + row per page, resume by skipping already-present `(chapter, page_number)`, bounded retry, pause on free-space floor. Foreground-only; a `WillPopScope`-style notice while active.
- **Offline reader:** reader page provider resolves `FileImage` from the store first, network second. Airplane-mode cold start must render a downloaded chapter end-to-end.
- **Progress outbox:** every progress save writes locally + enqueues; flush on connectivity/app-resume via `/reader/progress/batch`; server merge is furthest-wins so replays are safe.
- **Sweep:** on launch + resume — read-then-expire (48 h after `read_at`, pinned exempt, never the open chapter), then pressure eviction oldest-read-first down to the floor.
- **UI:** Downloads tab lists saved series/chapters with real on-device sizes; per-chapter and per-series download buttons in sources/library/reader; pin toggle; storage screen shows device bytes (not server bytes).

## 4. OCR channel

- Dart: `OcrEngine.recognize(List<String> imagePaths) → List<PageText>` over MethodChannel `mm/ocr`; feature flow = pick a downloaded chapter → run per page → `POST /ocr/chapter {…, pages:[{page,text,boxes}]}`. Search screen hits `/ocr/search`; coverage endpoint drives "OCR this chapter" affordances.
- iOS: `VNRecognizeTextRequest` in Swift (Runner target — **no pod, Podfile.lock unchanged**).
- Android: ML Kit `TextRecognition` via `app/build.gradle` dependency + Kotlin handler.
- Absent/failed platform impl → feature hidden.

## 5. Feature slices (agent work order)

| Slice | Scope |
|---|---|
| **M1 foundation** | Models + dio repositories + providers rekeyed; library/sources/auth/profiles/updates screens compile against new API; delete server-downloads feature; `flutter analyze` + `flutter test` green (rewrite broken tests, delete dead ones). |
| **M2 reader** | Manifest-driven reader, source-native progress (+ outbox stub), prev/next via manifest keys, per-series prefs preserved. |
| **M3 store** | §3 in full: sqflite store, queue, offline reader path, sweep, Downloads UI, storage screen. |
| **M4 OCR** | §4. |
| **M5 builds** | Local `flutter build apk --release --dart-define=FLAVOR=prod --dart-define=API_URL=https://app.manhwamaniacs.xyz` → scp to `/srv/manhwamaniacs/apk/app-release.apk`; retarget `.github/workflows/ios-build.yml` to this branch; new `ops/vps/fetch-ios-build.sh` (+ systemd timer or cron on the VPS) that downloads the newest release IPA (anon, or via optional token file at `/srv/manhwamaniacs/.gh_token`) into `/srv/manhwamaniacs/ipa/`; verify `app.manhwamaniacs.xyz` serves the install page + APK + `source.json`. Run `flutter clean` between tests and APK builds (shader-cache gotcha). |

## 6. Blocked on the user (not started by agents)

1. GitHub push auth from this laptop (add key / PAT) — gates the iOS cloud build.
2. Repo visibility (public → anon IPA download) or a fetch PAT on the VPS.
3. SideStore source add + install on the iPhone.

## 7. Open questions (agents decide, note in reports)

- O-1: per-page auth-gate write amplification (session `last_used_at` per page fetch) — acceptable v1; a bulk endpoint is a later backend mini-spec if it bites.
- O-2: Android OCR ships v1 or stubs — implementer's call by effort; iOS is the priority.
- O-3: keep or drop the old `setup` (server-URL) screen given the baked URL — keep, hidden behind Settings (escape hatch).
