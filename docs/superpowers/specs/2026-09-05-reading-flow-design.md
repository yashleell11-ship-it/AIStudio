# Reading flow: continuous scroll, Read-all, offline-first, bulk downloads (1e)

**Date:** 2026-09-05
**Status:** Design — build-through. Owner's requests, captured verbatim below.
**Branch:** `feat/vps-slim-source-native`.

## 1. What the owner asked for (verbatim intent)

> "first the autonext when i reach the bottom page i want u to optimize it the best like it
> should feel like scolling so i can view the chap 1 last and chap 2 starting not like i go
> to chapter 2 directly"

> "2nd for if i wanna see a manhwa and it have 100s of chapter i dont wanna do down wait it
> should be like 1 sijngle chapter evreything merge like if it have 30 chapter ill watch it
> in 1 chapter without feeling it it doesnt matter if it takes some time to load the manhwa
> but i want that mode too. there should be a small clickable button when i click a manhwa
> there is read online there should be one for read all and ofc read online for as usual"

> "3rd if the mahhwa is already downloaded it i think still waited a little and with network
> try to run that onpine not from the device if the manhwa is downloaded it should run from
> phone not from network even if it have the network"

> "also get multi download back so i can download 10 chapters in 1 go"

> "add download whole series for novels too"

## 2. R1 — Seamless chapter boundary (manga reader)

Today's auto-next swaps to the next chapter when the current one ends. The owner wants the
boundary to be *scrollable*: the last page of chapter N and the first page of chapter N+1
visible in the same scroll, no transition that interrupts.

- The next chapter's manifest and first pages **prefetch before** the reader reaches the
  boundary, so the seam never stalls.
- Scrolling **backwards** across the seam must work too — a boundary you can only cross one
  way is a trap.
- A quiet divider marks the change (which chapter you are entering) without stopping the
  scroll; progress/tracking must attribute pages to the correct chapter on both sides.
- Applies to the web and mobile manga readers. The novel reader already does seamless
  continuation — reuse its mechanism rather than adding a third.

## 3. R2 — "Read all" mode

A series page gets a second entry point beside **Read online**: **Read all**, which presents
the entire series as one continuous scroll — 30 chapters read as one, boundaries only
marked, never blocking.

- Chapters load progressively (windowed): the reader must never hold hundreds of chapters'
  images in memory. Load ahead, release far-behind, keep scroll position stable.
- The owner explicitly accepts a slower initial load. It must still stream — a spinner in
  front of 300 chapters is not acceptable, showing chapter 1 in normal time while the rest
  fills in behind is.
- Progress must keep working: reading into chapter 12 of a Read-all session records chapter
  12, so leaving and resuming lands correctly and furthest-wins merge is unaffected.
- The entry point is a small control on the series page, not a mode buried in settings.

## 4. R3 — Offline-first when downloaded (mobile)

Current mobile reader order is: fetch the manifest, fall back to the on-device store on
failure. That is backwards for a downloaded chapter — the reader waits on the network for
content already on the phone.

**New rule: if a chapter is fully downloaded, render it from disk immediately, without
waiting on any network call**, even with connectivity. The network is then only for what the
device does not have (adjacent-chapter keys, progress sync), and never blocks first paint.

- Partially-downloaded chapters: serve the pages present from disk, fetch only the gaps.
- The existing store already verifies each blob exists and is non-empty, so a hand-deleted
  file still falls back to network for that page only.

## 5. R4 — Bulk chapter download (mobile)

Restore multi-select downloading: choose N chapters (e.g. 10) and enqueue them in one action.
The chapter tile already carries an unused `selection` slot from the M3 work.

- Multi-select mode on the series chapter list, plus obvious range helpers ("next 10",
  "all unread") since selecting ten rows by hand is the thing being replaced.
- Everything enqueues through the existing `DownloadQueueController` — the cap, the ~1.5 GB
  free-space floor, pause/resume and per-item retry all apply unchanged. Bulk must never
  bypass the guards.

## 6. R5 — Download a whole novel series

Novels get the same, at series granularity: download every chapter of a book for offline
reading. Chapter text is tiny next to page images, so a whole novel is cheap — but it must
still go through the same queue, cap and retention rules, storing paragraphs as blobs in the
existing content-addressed store.

## 7. Slices

| Slice | Scope |
|---|---|
| R1 | seamless chapter boundary — mobile + web manga readers |
| R2 | Read-all continuous mode + series-page entry point |
| R3 | offline-first resolution when a chapter is on disk |
| R4 | bulk chapter selection and download |
| R5 | whole-novel download |

R3 and R4 are mobile-only (the web has no on-device store). R1 and R2 are both clients.
