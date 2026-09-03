> **Written against the old NAS-primary model, largely built since as phone-only
> (2026-09 pivot).** The original framing below — "download" fills the *NAS* and
> the phone mirrors from it — is gone: there is no server-side library or
> `/downloads` volume any more (see
> [`superpowers/specs/2026-09-03-backend-source-native-design.md`](superpowers/specs/2026-09-03-backend-source-native-design.md)).
> Clients pull chapter bytes straight through the source image proxy and this
> file's local-store/eviction/read-then-expire design is what actually got
> built at `mobile/lib/features/downloads/` (mobile spec:
> [`superpowers/specs/2026-09-03-mobile-source-native-design.md`](superpowers/specs/2026-09-03-mobile-source-native-design.md)
> §3). The **Transport** section below describes a bulk CBZ-archive design that
> was *not* what shipped — see the note there. Everything else on this page —
> the store layout, isolation, progress merge, and eviction rules — is still
> the reference for how the phone store works, now built rather than planned.

# Offline reading — design

True on-device offline reading: chapters stored on the **phone**, readable with no server and no
internet.

Status: **built.** The store, download queue, offline reader path, and
read-then-expire sweep described below shipped as mobile milestone M3 (see
`mobile/lib/features/downloads/`); OCR (§4 of the mobile spec) has not.

---

## Owner's decisions (binding)

| Question | Decision |
|---|---|
| One tap or two? | **One.** Tapping Download fills the **phone**. (Originally specified as "fills the NAS *and* the phone" — the NAS side no longer exists; there is nothing left to fill but the phone.) |
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
- **Only device bytes are deleted.** There is no server copy to be untouched any more — a re-read
  re-fetches through the source proxy rather than re-scraping a NAS.
- **Progress and read state survive.** Deleting the blobs must not delete the on-device chapter
  row's history or the `progress_outbox` entry — the chapter goes back to "known, not on phone", not
  to "never read". Getting this wrong would silently rewind the user's position.
- **Blobs are refcounted.** With cross-profile dedupe, a shared blob is only unlinked when the last
  referencing profile expires it.
- The interval is a constant, surfaced in Settings so it can be changed or turned off without a
  rebuild.

---

## Architecture

### 1. Transport — as built (not the bulk-archive design originally proposed)

> The original version of this section proposed a bulk `ZIP_STORED` CBZ archive
> endpoint, on the theory that per-page requests would drown SQLite in write
> transactions on a NAS. That endpoint was never built. What shipped instead
> is simpler, because it targets a stateless connector proxy rather than a
> local disk scan: one manifest call, then plain per-page HTTP fetches.

`GET /reader/chapter/manifest?source=&series=&chapter=` (`routes/reader.py`)
is the download plan: the ordered page list plus prev/next chapter keys —
`ReaderService.manifest()`. It carries no bytes and no local ids, only the
opaque `(source_id, series_key, chapter_key)` triple and each page's proxy
URL.

The queue then fetches every page individually through the existing
`GET /sources/{source}/pages/{page:path}/image` proxy — `ChapterPageFetcher`
in `mobile/lib/features/downloads/services/chapter_page_fetcher.dart`, one
`Dio` GET per page, same bearer token and `X-Profile-Id` header as every other
call. There is no server-side archive step and no per-page content hash from
the server; the on-device blob store content-addresses what it downloads
itself (see §2).

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

This section originally staged the work as a 6-step, 5–6 week plan built around
the two-destination NAS+phone model and a CBZ-backed library. That plan was
superseded by the source-native pivot; the actual build order is the mobile
spec's slice list —
[`superpowers/specs/2026-09-03-mobile-source-native-design.md`](superpowers/specs/2026-09-03-mobile-source-native-design.md)
§5 (M1–M5). See [CLAUDE_HANDOFF.md](CLAUDE_HANDOFF.md) §5 for which of those
have actually landed.

---

## Spikes from the original design (resolved or moot)

The Caddy-zip-snippet and CBZ-extraction-cost spikes below applied only to the
bulk-archive transport that was never built (see §1's note) and are moot.
`sqflite`'s `Podfile.lock` byte-identity resolved itself: M3 shipped with
`sqflite` as a direct dependency and the iOS build still works. Whether
app-storage data survives a SideStore re-sign is still believed rather than
proven by a dedicated experiment — see [ARCHITECTURE.md](ARCHITECTURE.md)'s
"iOS distribution" section for the current claim and reasoning.

## Known limitation

**iOS downloads are foreground-only.** Reliable background transfer needs a native background
`URLSession`, i.e. a new pod and a CI-only Podfile.lock — the exact thing this project's iOS setup
avoids. Pulling a large series means keeping the app open.

## Landmines

- **Never encrypt the store with a `flutter_secure_storage` key.** A re-signed sideloaded iOS build
  can lose the keychain. If the key became unreadable, every downloaded chapter would be
  permanently unreadable — the exact failure offline reading exists to prevent. `downloads_store.dart`
  and `blob_store.dart` do not use it; keep it that way.

The other landmines originally listed here (`page.id` rowid instability, a
shared-response-shape drift between `/reader/*` and `/library/*`, a
`BackgroundTask`-on-the-archive ETag bug) were all specific to the deleted
int-keyed catalog and the CBZ archive endpoint that was never built. They no
longer apply to the source-native code.

## Pre-existing bugs (from the original NAS-era design — now moot)

This design also originally listed three "pre-existing bugs" found in the
NAS-era local-catalog code (a CBZ page-ordering mismatch, a cross-profile
scroll-position leak, and unscoped reader endpoints). All three are moot: the
CBZ import path and the numeric-chapter-id reader endpoints they applied to no
longer exist, and the scroll-position leak was independently fixed — see
`frontend/src/features/reader/scroll-storage.ts`, which is now
per-(user, profile) scoped.
