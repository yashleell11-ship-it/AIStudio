# Next up: three owner-reported download bugs (diagnosed, not yet fixed)

Reported 2026-09-04 from real use of the shipped 1.9.0 build. All three are in
`mobile/`, which was held by another agent when they were diagnosed. Root causes are
confirmed by reading the code, not guessed.

## 1. Offline reading is unreachable from the library (most important)

The reader is NOT the bug. `resolvedReaderChapterProvider`
(`lib/features/reader/providers/reader_chapter_provider.dart`) already tries the manifest
and falls back to `buildOfflineReaderChapter` on ANY error; `sourceReaderChapterProvider`
does the same. That is why reading works from the Downloads tab.

The dead end is the screen you must pass through.
`lib/features/library/providers/series_detail_provider.dart` is network-only in full:

```dart
final result = await repo.getSeries(seriesId);
if (result.isErr) throw result.error;
```

`series_detail_screen.dart:53` watches it and renders error+retry, so offline the library
series page never reaches its chapter list and the offline-capable reader behind it cannot
be opened. Check `source_series_detail_screen.dart` for the same shape.

**Fix:** give the series-detail path the store-first/network-second treatment the reader
already has. Offline, a followed series with downloaded chapters must still open and list
at least those chapters, marked as the offline subset — never a full-screen error when the
store could answer. Reuse `DownloadsStore` (`listChapters`; the scope provider returns null
with no active profile) rather than building a parallel path.

## 2 + 3. Download progress and downloaded-state invisible in the series

Single root cause — `lib/features/downloads/widgets/chapter_download_action.dart` collapses
three distinct states into one identical widget:

```dart
DownloadChapterState.queued ||
DownloadChapterState.downloading ||
DownloadChapterState.complete =>
  SeriesChapterDownloadAction(buttonKey: buttonKey),
```

`SeriesChapterDownloadAction` (`lib/shared/widgets/series_detail/series_chapter_tile.dart:29`)
carries only `onPressed`, `retryable`, `buttonKey`; a null `onPressed` renders a disabled
button. Its own doc comment concedes it means "already downloaded, already queued, or
mid-request". So a chapter actively downloading, one queued, and one fully on disk are
pixel-identical, and progress has nowhere to render.

**Fix:** give the action a real state plus progress, so a row distinguishes
not-downloaded / queued / downloading-with-progress / downloaded / failed-retryable at a
glance. Check what `ChapterDownloadStatus` exposes and extend it if pages-done is absent.
The widget is shared by the library and source series pages — keep one fix covering both,
do not fork them. A downloaded chapter needs an unmistakable persistent marker, not a
disabled button.

Series-level download progress should also be visible on the series page itself, not only
in the Downloads tab: the owner started a series download and could not tell it had begun.

## Not a bug, but must be surfaced

Downloads pause whenever the app is backgrounded — a sideloaded iOS build has no reliable
background execution. This is by design (spec §3, foreground-only) and is the likely
explanation for a download that "looked stalled". The UI must state the reason.

## Regression tests to add

Mirror `mobile/test/features/downloads/offline_reader_acceptance_test.dart`, which fakes
offline by having every repository call fail with the exact `NetworkError` a real Dio call
throws. Add one proving the library series page still lists downloaded chapters when every
network call fails.

Gates: `flutter analyze lib` clean, `flutter test` never below 626.
