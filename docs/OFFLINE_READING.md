# Offline reading — design

True on-device offline reading: chapters stored on the **phone**, readable with no server and no
internet. Today "download" means the *NAS* fetches a chapter and the phone streams every page from
it, so a downloaded chapter is unreadable the moment the server is unreachable.

Status: **designed, not built.** Nothing here ships until the whole feature is complete.

---

## Owner's decisions (binding)

| Question | Decision |
|---|---|
| One tap or two? | **One.** The existing Download button fills the NAS *and* the phone. No second action. |
| Storage cap | **No limit** by default. The ~1.5 GB free-space floor is non-negotiable regardless. |
| When full | **Auto-evict** the oldest already-read chapters. Pinned series are never evicted. |
| After reading | **Auto-delete the phone copy 2 days after a chapter is finished.** See below. |
| Download a series | **Every chapter** goes to the phone, not just the next N unread. |
| Two profiles, same chapter | **Store once**, deduplicated by content hash. Each profile still only sees its own. |

Consequence of "no limit" + "everything" + auto-evict: the free-space floor is the only brake, and
eviction can only reclaim *finished* chapters. On a series where nothing has been read there is
nothing to evict, so the queue pauses at the floor rather than deleting unread chapters. That is
deliberate — silently deleting something unread is worse than stalling.

### Read-then-expire (the 2-day rule)

Finishing a chapter schedules its **phone copy** for deletion 2 days later. This is the primary way
storage stays bounded; pressure-based eviction becomes the fallback for when reading outpaces it.

Precise semantics, because each of these is a way to get it wrong:

- **Trigger** is a chapter reaching `read_complete`, not merely being opened. Stamp `read_at`;
  delete when `now - read_at >= 48h`.
- **The sweep runs on app launch and resume, never on a timer.** There is no dependable background
  execution on a sideloaded iOS build, so "2 days later" in practice means "on the first app open
  after 48 hours have elapsed". Anything else would be a promise the platform cannot keep.
- **Re-reading cancels it.** Reopening a chapter clears `read_at`; finishing it again restarts the
  48 hours. Otherwise a re-read would delete itself mid-scroll.
- **Never delete the chapter currently open**, even if its timer has expired.
- **Pinned series are exempt**, same as pressure eviction.
- **Only device bytes are deleted.** The NAS copy is untouched, so a re-read re-downloads rather
  than re-scrapes.
- **Progress and read state survive.** Deleting the blobs must not delete the `chapters` row's
  history or the `progress_outbox` entry — the chapter goes back to "on server, not on phone", not
  to "never read". Getting this wrong would silently rewind the user's position.
- **Blobs are refcounted.** With cross-profile dedupe, a shared blob is only unlinked when the last
  referencing profile expires it.
- The interval is a constant, surfaced in Settings so it can be changed or turned off without a
  rebuild.

---

## Architecture

### 1. Transport — one request per chapter, not forty

Every page fetch traverses the global auth gate, and `AuthService.resolve_session` ends by stamping
`last_used_at` and calling `db.commit()`. A 40-page chapter is therefore **40 SQLite write
transactions**, serialised by SQLite's single-writer rule and competing with the download workers. A
100-chapter series is 4,000. Bulk transfer is a correctness concern, not an optimisation.

Two new endpoints on `routes/reader.py`:

- `GET /reader/chapter/{id}/manifest` — the download plan: page count, `content_hash`, adjacency,
  and per-page `{number, filename, media_type, size, sha256}`.
- `GET /reader/chapter/{id}/archive` — an **uncompressed (`ZIP_STORED`) CBZ**, built once to a
  cached file and served with `FileResponse`.

The per-page hashes cost nothing: the download pipeline already writes them to
`.manhwamaniacs-download.json` (`ChapterManifest`, `services/download_support.py`).

`ZIP_STORED` because page bytes are already JPEG/PNG/WebP so DEFLATE burns NAS CPU for nothing;
because the codebase already treats CBZ as a first-class container so the output is re-importable;
and because stored members sit at known offsets, giving the phone a zip-decoder-free fallback.

A **cached file** rather than a stream because Starlette's `FileResponse` implements
Range/206/`If-Range`/416/ETag and `StreamingResponse` gives none of it.

Three things must never enter the manifest: `page.id` (destroyed and reassigned on rescan — key on
`(chapter_id, page_number)`), `file_path` (absolute container paths), and `remote_url` (the upstream
scanlation URL).

### 2. Local store — sqflite, one DB plus a content-addressed blob tree

`sqflite_darwin` is **already a resolved pod** in `mobile/ios/Podfile.lock`, pulled in transitively
by `flutter_cache_manager` — SQLite compiles into the shipping `.ipa` today. Promoting it to a direct
dependency changes zero native build inputs, which matters enormously because `mobile/ios/Podfile`
exists specifically so `pod install` touches the network zero times, and a Podfile.lock can only be
regenerated by the cloud Mac. isar and drift's default backend each vendor a new native SQLite
binary — a new pod on the one platform with the worst feedback loop.

Files live under `getApplicationSupportDirectory()`, explicitly **not** `getTemporaryDirectory()`:
that is iOS `NSCachesDirectory`, which the OS purges under pressure and which the existing
"clear image cache" action wipes wholesale.

Isolation is enforced structurally, not by convention: `scope_id` (user + profile) is the leading
column of every content primary key, the store takes its scope in the **constructor** and its
provider returns `null` rather than a default scope when either half is missing, and its providers
join `profileScopedInvalidators`. No scope → no store → the UI shows "nothing downloaded". It cannot
render another profile's.

### 3. Reader integration and progress

`ReaderPage.imageUrl` becomes an `ImageProvider` at exactly two call sites. The rendering widget
already takes an `ImageProvider`, so a `FileImage` slots in with no layout change.

Progress is a **state map, not a log**. Merge rule: **furthest-wins on `(chapter.number, page)`**,
`updated_at` as tie-break only, `is_completed` sticky. Not last-write-wins — LWW silently rewinds
you from chapter 14 to 11 and you don't notice until you hit a scene you've read, whereas
furthest-wins fails by jumping a deliberate re-read forward, which is obvious and one tap to undo.
LWW would also rest on a client clock the server has never seen.

No background isolate: the iPhone build is sideloaded and has no dependable background execution.

---

## Stages

Each is independently reviewable. Riskiest unknowns first.

1. **Prove the two irreversible bets** (~1 week). Does Range/resume survive Caddy *and* the
   Cloudflare tunnel, and is the CI-generated `Podfile.lock` byte-identical after adding sqflite?
   Nothing is readable yet — this stage buys certainty.
2. **Read from the phone with no server** (~1 week). Airplane mode, cold start, read a chapter end
   to end. The payoff lands in week two, not week five.
3. **One tap, two destinations** (~1–1.5 weeks). A queue engine: two sequential legs, resume,
   bounded retry, disk floor, ghost-row recovery after a kill.
4. **Offline progress that never rewinds you** (~4–5 days).
5. **Storage: budget, eviction, honest numbers** (~1 week). Includes the read-then-expire sweep and
   its Settings control. The Storage screen currently conflates NAS bytes with phone bytes.
6. **Platform hardening and the CBZ-backed library** (~4–5 days).

Realistically **5–6 weeks**.

---

## Spike before committing

- **The Caddy `zip` snippet** is defined in `/srv/caddy/conf.d`, outside this repo. If it compresses
  without a content-type matcher it can strip `Content-Length`/`Accept-Ranges` and defeat resume.
  Curl a `Range` request through the real hostname before promising resume.
- **Podfile.lock byte-identity** after adding sqflite — inference until a CI run proves it.
- **ZIP extraction cost on-device** for a 20 MB CBZ. Fallback: members are `ZIP_STORED`, so the
  manifest can carry byte offsets and the phone can slice with `RandomAccessFile`, no decoder.
- **Does app-storage data survive a SideStore re-sign?** Currently believed from `IOS_SIDELOAD.md`,
  not from an experiment. Test with a throwaway file across one 7-day cycle before trusting a
  multi-GB shelf to it.

## Known limitation

**iOS downloads are foreground-only.** Reliable background transfer needs a native background
`URLSession`, i.e. a new pod and a CI-only Podfile.lock — the exact thing this project's iOS setup
avoids. Pulling a large series means keeping the app open.

## Landmines

- **Never encrypt the store with a `flutter_secure_storage` key.** `auth_controller.dart` already
  guards keychain writes because a re-signed sideloaded build can lose them. If the key became
  unreadable, every downloaded chapter would be permanently unreadable — the exact failure offline
  reading exists to prevent.
- **`page.id` is not stable** across rescans; SQLite reuses freed rowids. Key on
  `(chapter_id, page_number)`.
- **Two endpoints already serve page bytes and two return chapter structure** (`/reader/*` and
  `/library/*`, same service methods). A response-shape change must land on both or they drift.
- **Do not attach a `BackgroundTask` cleanup to the archive.** Starlette runs background tasks after
  *every* response including each 206, so a per-request rebuild changes the mtime, changes the
  mtime-derived ETag, fails `If-Range`, and forces a restart from byte zero.

## Pre-existing bugs found during this design

Independent of offline reading, worth fixing regardless:

- `get_chapter` emits absolute container filesystem paths to the client, contradicting the
  deliberate path-hiding in `image_service.py`.
- Archive-backed (CBZ) chapters resolve page→member by lexicographic sort, which disagrees with the
  sort the scanner used, so **page N can already serve the wrong image** for imported CBZs.
- Reader scroll positions are keyed `manhwamaniacs-reader-scroll:<chapterId>` with no user or
  profile — cross-profile leakage on a shared device.
- The reader endpoints are **not ownership-scoped**: `get_chapter` filters on chapter id alone with
  no membership check, so any authenticated household member can fetch any chapter. Today's library
  isolation work did not cover this path.
