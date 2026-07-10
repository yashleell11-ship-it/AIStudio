# Implementation Spec: Reader Stability
**Agent:** Cursor Chat 1  
**Architect sign-off:** Chief Software Architect  
**Date:** 2026-07-01  
**Status:** Ready to implement

---

## 1. Goals

Bring the chapter reader to production quality: eliminate all known scroll/render bugs, make progress saving reliable for both local and online chapters, add resilience against image load failures, and remove development noise from production builds.

This sprint does **not** include: new reader modes, RTL reading direction, double-page spread, or AI-powered features.

---

## 2. Scope

### In scope
- Fix `window.setTimeout` race condition in `ChapterReader.updateScrollState`
- Fix scroll restoration that silently fails when images haven't loaded yet
- Add React error boundary to both reader paths (local + online)
- Add image load error handling with retry in `PageImage`
- Make `readerDebug` calls zero-cost in production (already gated — verify it stays gated)
- Prevent duplicate progress saves when the page hasn't actually changed
- Save reading progress for online chapters (currently missing in `SourceReader`)
- Fix `progressTimerRef` cleanup leak in `BasicReader`
- Add loading skeleton for the chapter content area
- Prevent chapter navigation to `null` hrefs from creating broken routes

### Out of scope
- Any backend changes
- Any database changes
- Any changes to `library_service.py`, `reader_service.py`, or any backend route
- Any new features not listed above

---

## 3. File Ownership

### Files this agent OWNS (safe to modify freely)
```
frontend/src/features/reader/components/BasicReader.tsx
frontend/src/features/reader/components/ChapterReader.tsx
frontend/src/features/reader/components/PageImage.tsx
frontend/src/features/reader/components/ReaderControls.tsx
frontend/src/features/reader/components/SourceReader.tsx
frontend/src/features/reader/components/VirtualPageList.tsx
frontend/src/features/reader/debug.ts
frontend/src/features/reader/hooks.ts
frontend/src/features/reader/scroll-storage.ts
frontend/src/features/reader/store.ts
frontend/src/features/reader/types.ts
frontend/src/features/reader/api.ts
frontend/src/features/reader/index.ts
frontend/src/features/reader/page-layout.ts
```

### New files this agent creates
```
frontend/src/features/reader/components/ReaderErrorBoundary.tsx
frontend/src/features/reader/components/ChapterSkeleton.tsx
```

### Files this agent MUST NOT modify
```
frontend/src/app/reader/[seriesId]/[chapterId]/page.tsx        ← page shell, leave as-is
frontend/src/app/reader/online/[sourceId]/[seriesId]/[chapterId]/page.tsx
frontend/src/app/reader/page.tsx
frontend/src/features/library/*                                 ← Kimi territory
frontend/src/features/downloads/*                               ← separate feature
frontend/src/features/sources/*                                 ← Kimi territory
frontend/src/lib/*
frontend/src/components/*
backend/**                                                      ← no backend changes
```

---

## 4. APIs This Agent May Use

All API calls go through `frontend/src/features/reader/api.ts`. Do not add new `http.*` calls directly in components.

Existing endpoints consumed:
- `GET /reader/chapter/{chapterId}` — chapter content (local)
- `POST /reader/progress` — save progress
- `GET /reader/progress/{seriesId}` — get saved progress
- `GET /reader/chapter/{chapterId}/adjacent?direction=previous|next` — adjacent chapter
- `POST /reader/bookmarks` — add bookmark
- `GET /sources/{sourceId}/series/{seriesId}/chapters/{chapterId}/reader` — online reader

No new backend endpoints are required for this sprint.

---

## 5. Database Changes

**None.** This spec is frontend-only.

---

## 6. Bug Fixes — Detailed Specifications

### BUG-1: `window.setTimeout` race in `updateScrollState` (ChapterReader.tsx:118)

**Problem:**  
```typescript
window.setTimeout(() => {
  writeScrollPosition(scrollKey, scrollTop);
}, SCROLL_SAVE_MS);
```
Every scroll event creates a new `setTimeout` without clearing the previous one. Fast scrolling creates hundreds of pending timers, all of which eventually fire and write to localStorage.

**Fix:**  
Add a `scrollSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)` to the component. In `updateScrollState`, clear the previous timer before setting a new one:
```typescript
if (scrollSaveTimerRef.current !== null) {
  clearTimeout(scrollSaveTimerRef.current);
}
scrollSaveTimerRef.current = window.setTimeout(() => {
  writeScrollPosition(scrollKey, scrollTop);
  scrollSaveTimerRef.current = null;
}, SCROLL_SAVE_MS);
```
The ref must be cleaned up in the `useEffect` cleanup that removes the scroll listener — call `clearTimeout(scrollSaveTimerRef.current)` there.

**Acceptance:** On a 200-page chapter, rapidly scrolling to the bottom and stopping should produce exactly one localStorage write after 250ms, not 200.

---

### BUG-2: `progressTimerRef` cleanup leak in `BasicReader.tsx:81`

**Problem:**  
```typescript
const progressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
```
This ref is used to debounce `persistProgress` but is never cleaned up on unmount. When the user navigates away mid-debounce, the timer fires after the component has unmounted and calls `saveProgress.mutate()` on a stale component instance.

**Fix:**  
Add a `useEffect` cleanup:
```typescript
useEffect(() => {
  return () => {
    if (progressTimerRef.current) {
      clearTimeout(progressTimerRef.current);
    }
  };
}, []);
```

**Acceptance:** Navigate to a chapter, scroll briefly, immediately navigate away. No `saveProgress` mutation is triggered after navigation completes (verify with React Query Devtools or network tab).

---

### BUG-3: Scroll restoration fails when images haven't loaded

**Problem:**  
The scroll restoration in `ChapterReader` (lines 140–178) runs `requestAnimationFrame` and attempts to scroll to a saved position or a page element. However, if images haven't loaded yet, the virtualizer's estimated heights are wrong — `estimateScrollOffsetToPage` returns a value based on estimated heights, but the actual scroll container height may be zero. The scroll fires, then images load and shift the layout, leaving the user at the wrong position.

**Fix:**  
Move scroll restoration to trigger after the first image loads, not on the `pages` array being populated. Use the `onImagesReady` callback from `VirtualPageList`:
1. Set `restoredScrollRef.current = false` when `pages` changes.
2. In `handleImagesReady`, if `!restoredScrollRef.current`, perform the scroll restoration.
3. Remove the `useEffect` that currently attempts restoration on pages load — it fires too early.

The restored scroll must still prefer `readScrollPosition` (saved pixel offset) over the page-number estimate. Fallback order:
1. Saved pixel offset from `localStorage` → `scrollElement.scrollTop = savedScroll`
2. Initial page > 1 → `scrollIntoView` on `#reader-page-{n}` element
3. Initial page = 1 → do nothing (already at top)

**Acceptance:** 
- Open a chapter at page 47 (via URL `?page=47`). After images load, the correct page is visible.
- Reopen the same chapter (same scroll key). The exact pixel scroll position from the last session is restored.
- Opening at page 1 does not scroll.

---

### BUG-4: Online chapters (SourceReader) don't save reading progress

**Problem:**  
`SourceReader` renders `ChapterReader` with `onPageProgress` as `undefined`. The page prop wires `onBookmark` but never connects `onPageProgress` to a `persistProgress` call. Online reading sessions are never recorded.

**Fix:**  
In `SourceReader`, mirror the `BasicReader` pattern:
1. Add `useSaveProgress()` hook.
2. Add the same `progressTimerRef` debounce pattern as `BasicReader`.
3. Wire `onPageProgress={handlePageProgress}` in the `ChapterReader` call.

Progress for online chapters saves to the same `POST /reader/progress` endpoint. The series ID and chapter ID for online chapters come from the resolved reader payload (`mode: "remote"`, `seriesId`, `id` fields). These must be converted to integers before the API call — the remote payload uses string IDs.

**Note for Kimi Agent 2:** When Library Intelligence ships character/event tracking, progress saving for online chapters being fixed here means online reading will also contribute to read-depth tracking. No cross-agent coordination required — the progress table is shared.

**Acceptance:**
- Read 5 pages in an online chapter. `POST /reader/progress` is called with the correct `series_id` and `chapter_id`.
- Navigate back to the library. The series shows correct reading progress.

---

### BUG-5: Chapter edge navigation fires on null href

**Problem:**  
`ChapterEdgePrompt` receives `href={previousChapterHref}` which is `null` when there's no previous chapter. The current guard in `ChapterReader` passes the href conditionally only when rendering the prompt component, but the keyboard shortcut handlers call `router.push(previousChapterHref)` without checking for null:
```typescript
const goPreviousChapter = useCallback(() => {
  if (previousChapterHref) {         // ← this guard is correct
    router.push(previousChapterHref);
  }
}, [previousChapterHref, router]);
```
This is correctly guarded. However, `goNextChapter` follows the same pattern — verify both are guarded and add a test case that pressing `l` on the last chapter produces no navigation.

**Acceptance:** On the last chapter, pressing `l` does not trigger a route change. On the first chapter, pressing `h` does not trigger a route change.

---

## 7. New Components — Specifications

### 7.1 `ReaderErrorBoundary.tsx`

**Purpose:** Catch render errors inside the reader so a crash in the virtualizer or a single page image doesn't destroy the entire page.

**Interface:**
```typescript
interface ReaderErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}
```

**Behavior:**
- Class component extending `React.Component` (error boundaries require class components)
- On error: render a centered fallback UI with the message "Failed to load chapter. Please try refreshing." and a "Go back" link using `window.history.back()`
- Log the error to `console.error` in development only (check `process.env.NODE_ENV`)
- Provide a `resetErrorBoundary` method that clears the error state — to be called when `scrollKey` changes (navigating to a new chapter should reset the boundary)

**Usage in `ChapterReader`:**
Wrap the entire return tree in `<ReaderErrorBoundary>`.

**Acceptance:**
- Throw a test error inside `VirtualPageList`. The fallback renders. No other part of the app crashes.
- Navigate to a different chapter. The error boundary resets and the new chapter renders normally.

---

### 7.2 `ChapterSkeleton.tsx`

**Purpose:** Replace the plain text "Loading chapter…" with a proper skeleton that matches the visual weight of the loaded content.

**Interface:**
```typescript
interface ChapterSkeletonProps {
  pageCount?: number; // default: 3 — number of page placeholders to show
}
```

**Visual spec:**
- Render `pageCount` stacked skeleton blocks
- Each block: full width, `aspect-ratio: 2/3` (portrait page default), background `var(--color-surface-2)`, CSS pulse animation using Tailwind's `animate-pulse`
- Match the max-width constraint of `VirtualPageList` (`max-w-3xl mx-auto`)
- Spacing between blocks: `gap-y-4`

**Usage:**
In `ChapterReader`, replace:
```typescript
if (isLoading) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center text-muted">
      Loading chapter…
    </div>
  );
}
```
With:
```typescript
if (isLoading) {
  return <ChapterSkeleton pageCount={3} />;
}
```

**Acceptance:**
- Navigating to a chapter shows the skeleton while loading, then the pages transition in cleanly.
- The skeleton's width matches the loaded content width at all viewport sizes.

---

## 8. Data Flow

```
User opens /reader/{seriesId}/{chapterId}?page=N
  │
  ├─ page.tsx (server) → renders <BasicReader key="{id}-{id}">
  │
  ├─ BasicReader
  │   ├─ useReaderChapter(chapterId)       → GET /reader/chapter/{id}
  │   ├─ useAdjacentChapter("previous")   → GET /reader/chapter/{id}/adjacent?direction=previous
  │   ├─ useAdjacentChapter("next")       → GET /reader/chapter/{id}/adjacent?direction=next
  │   └─ renders <ChapterReader chapter={...} onPageProgress={handlePageProgress}>
  │       │
  │       ├─ Mounts: attempts scroll restore (deferred to onImagesReady)
  │       ├─ Scroll events → debounced localStorage write (fixed timer)
  │       ├─ Page visibility → onPageProgress → handlePageProgress
  │       │     └─ debounced 500ms → persistProgress → POST /reader/progress
  │       ├─ Keyboard h/l → router.push(prev/nextChapterHref)
  │       ├─ Keyboard b → addBookmark → POST /reader/bookmarks
  │       └─ <VirtualPageList> → onImagesReady → triggers scroll restoration
  │
  └─ ReaderErrorBoundary wraps everything above
```

---

## 9. Edge Cases

| Scenario | Expected behavior |
|---|---|
| Chapter has 0 pages | Show "This chapter has no pages." message (current behavior, preserve) |
| Image URL returns 404 | `PageImage` shows error state with retry button (see BUG fixes) |
| `localStorage` is unavailable (privacy mode) | `readScrollPosition` and `writeScrollPosition` must catch `SecurityError`; fail silently |
| User scrolls during restore debounce | The saved position wins — do not fight with the user's scroll |
| `seriesId` or `chapterId` is NaN | `page.tsx` already guards with `Number(seriesId)` — add `Number.isFinite()` check and render 404 if invalid |
| Adjacent chapter query returns 404 | `useAdjacentChapter` returns `null`; prev/next hrefs are `null`; keyboard shortcuts do nothing |
| Progress save fails (network error) | Silent failure — do not show an error toast, do not block the reader |
| Chapter re-render with same `chapterId` | `restoredScrollRef` must NOT reset — only reset on `chapterId` change |

---

## 10. Error Handling

| Error | Handler |
|---|---|
| Chapter fetch fails | `ChapterReader` renders error state with `error.message` (existing behavior) |
| Adjacent chapter fetch fails | Treat as no adjacent chapter — `href` becomes `null` |
| Progress save fails | Silent — TanStack Query will retry per its config; reader stays functional |
| Bookmark save fails | Silent for now |
| Image load error | `PageImage` must catch `onError`, show a retry button; retry up to 3 times with 1s delay |
| Render crash | `ReaderErrorBoundary` catches, shows fallback |

### Image retry spec for `PageImage`:

Add local state: `const [failCount, setFailCount] = useState(0)`.  
On `onError`: if `failCount < 3`, increment and re-render (the `src` with a cache-bust `?retry={failCount}` suffix forces a new fetch). If `failCount >= 3`, show a `<div>` with "Failed to load image" text and a "Retry" button that resets `failCount` to 0.

---

## 11. Performance Considerations

- `VirtualPageList` already uses `@tanstack/react-virtual` — do not add any additional scroll listeners inside individual page components
- `PageImage` is wrapped in `memo()` — keep it that way; do not add props that change on every render
- `VirtualPageRow` is wrapped in `memo()` — the `onImageLoad` callback is created inline in the parent; it must be stable via `useCallback` to prevent unnecessary re-renders of all rows on any scroll event
- The `onImageLoad` callback in `VirtualPageList` currently calls `virtualizer.measureElement(element)` and `reportVisiblePage()` — this is correct; do not move these calls elsewhere
- Do not add any `console.log` or `readerDebug` calls that aren't already behind the `ENABLED` guard in `debug.ts`

---

## 12. Security Considerations

- Image `src` values come from `pageImageUrl(pageId)` which constructs `/reader/page/{id}/image` — the ID is a number from the API response, not user input; no XSS risk
- For online chapters, `imageUrl` comes from `toRemoteReaderChapterContent()` which only uses URLs that start with `http` (passing them through directly) or prefixes with `env.apiUrl` — do not change this logic
- The `writeScrollPosition` call writes only `Math.round(scrollTop)` — a number — to localStorage; no string sanitization needed
- Do not add any `dangerouslySetInnerHTML` anywhere in this feature

---

## 13. Testing Requirements

All tests go in `frontend/src/features/reader/__tests__/`.

### Required tests

**`scroll-storage.test.ts`**
- `writeScrollPosition` stores a rounded integer
- `readScrollPosition` returns null for missing key
- `readScrollPosition` returns null for invalid (NaN, negative) stored values
- `readScrollPosition` returns the stored value for valid input
- Both functions handle unavailable localStorage (mock `localStorage.getItem` to throw `SecurityError`)

**`ReaderErrorBoundary.test.tsx`**
- Renders children normally when no error occurs
- Renders fallback when a child throws during render
- Resets error state when `key` prop changes (simulating chapter navigation)

**`PageImage.test.tsx`**
- Renders with correct `src` and `alt`
- Calls `onLoad` when image loads
- Increments retry count on `onError` up to 3 times
- Shows retry UI after 3 failures
- Retry button resets the failure count

**`ChapterReader.test.tsx`**
- Does not navigate on `h` when `previousChapterHref` is null
- Does not navigate on `l` when `nextChapterHref` is null
- Calls `onPageProgress` with the correct page number on scroll
- `writeScrollPosition` is called exactly once after debounce, not on every scroll event

---

## 14. Acceptance Criteria

This sprint is complete when ALL of the following pass:

- [ ] `npm run build` exits 0
- [ ] `npm run typecheck` exits 0
- [ ] `npm run lint` exits 0
- [ ] All tests in `frontend/src/features/reader/__tests__/` pass
- [ ] Open a 200-page chapter, scroll quickly to the bottom: localStorage receives exactly 1 write per 250ms window (not 200 writes)
- [ ] Close and reopen the same chapter: scroll position is exactly restored
- [ ] Navigate away mid-debounce: no `POST /reader/progress` fires after navigation
- [ ] Force an image 404: retry button appears after 3 attempts; clicking it resets retry count
- [ ] Force a render crash in `VirtualPageList`: `ReaderErrorBoundary` fallback renders; rest of app is unaffected
- [ ] Read 10 pages of an online chapter: `POST /reader/progress` is called with correct IDs
- [ ] Press `l` on the last chapter: no navigation occurs, no console error
- [ ] Press `h` on the first chapter: no navigation occurs, no console error
- [ ] Chapter loading shows `ChapterSkeleton`, not bare text
- [ ] No `readerDebug` output appears in a production (`NODE_ENV=production`) build

---

## 15. Merge Risks

**Risk 1 — `ChapterReader.tsx` is the central file for this sprint.**  
If Cursor Chat 2 (auto-update) adds a global notification banner that interferes with the reader layout, the reader's scroll calculations could be affected. Coordinate: the banner must be rendered in `app-shell.tsx` outside the scroll container, not inside the reader layout.

**Risk 2 — `frontend/src/features/reader/hooks.ts`.**  
If any other agent imports from `features/reader/hooks.ts` (unlikely but possible), the `useAdjacentChapter` hook signature must remain stable: `(chapterId: number, direction: "previous" | "next") => UseQueryResult<AdjacentChapter | null>`.

**Risk 3 — `debug.ts` is already correctly gated.**  
The existing `const ENABLED = process.env.NODE_ENV === "development"` guard is correct. Do not change it.

---

## 16. Future Extensibility

Design these components so the following can be added in future sprints without rewriting:

- **Right-to-left (manga) mode:** `ChapterReader` should accept a `direction: "ltr" | "rtl"` prop (not yet implemented — just ensure the layout uses flex-column so reversing is a single prop change)
- **Double-page spread:** `VirtualPageRow` renders one page per row. A future `mode: "spread"` could render two pages side-by-side by changing the row component, not the virtualizer
- **Chapter preloading:** `BasicReader` should be able to accept a `prefetchNextChapterId` prop that TanStack Query can use — the hook signature already supports this pattern
- **Offline mode:** `scroll-storage.ts` wraps localStorage already. A future implementation can swap it for IndexedDB by keeping the same `readScrollPosition`/`writeScrollPosition` interface
