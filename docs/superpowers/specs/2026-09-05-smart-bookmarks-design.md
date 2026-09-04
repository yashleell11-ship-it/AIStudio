# Smart bookmarks: exact position, offline, both media (1g)

**Date:** 2026-09-05
**Status:** Design — build-through.
**Branch:** `feat/vps-slim-source-native`.

## 1. What the owner asked for

> "add bookmark offline and all the bookmark must be smart annd all page and all exactly
> where it left"

Three things: bookmarks must work **offline**, must record the **exact** position rather
than a page number, and must exist for **both media** (the novel reader currently has no
bookmark control at all).

## 2. Where it stands today

- `Bookmark` (backend/database/models.py) stores `(source_id, series_key, chapter_key,
  page: int, note)`. Page granularity only.
- `ChapterProgress` already stores `scroll_offset_px` — so **resume is more precise than a
  bookmark**, which is backwards.
- The on-device store (`mobile/lib/features/downloads/store/`) has `saved_chapters`,
  `saved_pages`, `blobs`, `progress_outbox` — **no bookmarks table**, so bookmarking is
  impossible offline and a bookmark made offline is lost.
- The novel reader has no bookmark affordance; the manga reader binds `b`.

## 3. Precision — what "exactly where it left" means per medium

A bookmark resolves to a position, and the position is medium-specific. Store enough to
land on the same pixel, and enough to degrade gracefully when the content changes.

**Manga** — `page` plus an offset *within* that page. Pages are long strips; a page number
alone can be thousands of pixels from where the reader was. Store the offset as a
**fraction of page height (0.0–1.0)**, not pixels: the same chapter renders at different
widths on phone and web, and a pixel offset is meaningless across them. Reuse the
reasoning already in `scroll_offset_px` but do not repeat its device-dependence.

**Novel** — `paragraph_index` plus a fraction within that paragraph. Paragraph indices are
stable for a given chapter's sanitized text, which the server caches, so the same bookmark
resolves identically on both clients.

Both also store `chapter_number` (float) so a bookmark still means something if a source
re-keys its chapters.

**Degrade honestly.** If the content changed and the recorded position no longer exists
(page count shrank, paragraph index out of range), land at the nearest valid position and
say so quietly rather than failing or silently jumping to the top.

## 4. Offline

Bookmarks join the on-device store as a first-class table, and sync the way progress
already does:

- A `bookmarks` table in the sqflite store, `scope_id` as the leading PK column like every
  other table, so one profile can never see another's.
- A **bookmark outbox** mirroring `progress_outbox` — create/delete offline, flush on
  connectivity and app resume.
- Reads come from the device first, so the Bookmarks screen works with no signal.
- Merge rule: bookmarks are **user-created objects, not a furthest-wins scalar**. A
  deletion must not be resurrected by a stale client replaying a create, and two devices
  creating different bookmarks must both survive. Use a client-generated id (uuid) plus a
  tombstone for deletes; do not reuse the progress merge.

## 5. Smart

- **Auto-resume stays what it is** (furthest-wins progress). A bookmark is a *deliberate*
  marker you return to; the two are different and must not be conflated.
- Bookmarking should capture the current position with **one action** — no dialog asking
  for a page. The note is optional and added after.
- The Bookmarks screen shows enough to choose between them without opening: series, chapter,
  a position indicator ("62% of chapter 14"), and for novels **a snippet of the text at that
  point**, which is what makes a prose bookmark recognisable.
- Tapping one opens the reader at exactly that position, not the chapter start.

## 6. Constraints

- Per `(user_id, profile_id)` scoping throughout — a cross-profile leak has shipped here
  before.
- The 18+ gate applies to bookmark listings exactly as it does elsewhere.
- Backend change needs an Alembic revision on the current head that upgrades a fresh DB
  cleanly, and must not lose existing bookmark rows — old page-only rows resolve to
  offset 0.0 of that page.
- Web and mobile ship the same capability; a bookmark made on one opens correctly on the
  other.
