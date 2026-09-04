import 'package:flutter/widgets.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';

/// Builds the trailing download control for one [SeriesChapterTile] from its
/// on-device [status] plus, for the one chapter the queue is fetching right
/// now, its live page counter — the single place the two chapter-row screens
/// (library series detail, source series detail — the reader has no row list)
/// agree on what each download state looks like.
///
/// Every store state maps to its own [SeriesChapterDownloadPhase]. They used
/// to collapse: queued, downloading and complete all became one disabled
/// button, so starting a download changed nothing on screen and a chapter
/// already on the phone looked like one the app simply refused to fetch.
///
/// `null` when [hasScope] is false: no active `(user, profile)` session means
/// no store, and a download button with nothing behind it is worse than none
/// — "no scope → UI shows nothing downloaded" extends to hiding the action
/// that would silently no-op.
SeriesChapterDownloadAction? chapterDownloadAction({
  required bool hasScope,
  required ChapterDownloadStatus? status,
  required VoidCallback onDownload,
  ChapterDownloadProgress? progress,
  Key? buttonKey,
}) {
  if (!hasScope) return null;

  return switch (status?.state) {
    null => SeriesChapterDownloadAction(
        phase: SeriesChapterDownloadPhase.notDownloaded,
        onPressed: onDownload,
        buttonKey: buttonKey,
      ),
    // `ensureQueued` resets a failed row to queued, so the same callback is
    // both "download" and "retry".
    DownloadChapterState.failed => SeriesChapterDownloadAction(
        phase: SeriesChapterDownloadPhase.failed,
        onPressed: onDownload,
        error: status?.error,
        buttonKey: buttonKey,
      ),
    DownloadChapterState.queued => SeriesChapterDownloadAction(
        phase: SeriesChapterDownloadPhase.queued,
        buttonKey: buttonKey,
      ),
    // A row can sit at `downloading` with no live counter — the app was
    // killed mid-chapter and this is work waiting to resume — so the page
    // numbers are only ever the queue's, never invented from the row.
    DownloadChapterState.downloading => SeriesChapterDownloadAction(
        phase: SeriesChapterDownloadPhase.downloading,
        pagesDone: progress?.pagesDone ?? 0,
        pageTotal: progress?.pageTotal ?? 0,
        buttonKey: buttonKey,
      ),
    DownloadChapterState.complete => SeriesChapterDownloadAction(
        phase: SeriesChapterDownloadPhase.downloaded,
        buttonKey: buttonKey,
      ),
  };
}
