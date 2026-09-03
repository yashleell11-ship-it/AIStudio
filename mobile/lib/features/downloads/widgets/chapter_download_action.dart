import 'package:flutter/widgets.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';

/// Builds the trailing download control for one [SeriesChapterTile] from its
/// on-device [status] — the single place the three chapter-row screens
/// (library series detail, source series detail — the reader has no row list)
/// agree on what each download state looks like.
///
/// `null` when [hasScope] is false: no active `(user, profile)` session means
/// no store, and a download button with nothing behind it is worse than none
/// — "no scope → UI shows nothing downloaded" extends to hiding the action
/// that would silently no-op.
SeriesChapterDownloadAction? chapterDownloadAction({
  required bool hasScope,
  required ChapterDownloadStatus? status,
  required VoidCallback onDownload,
  Key? buttonKey,
}) {
  if (!hasScope) return null;

  return switch (status?.state) {
    null => SeriesChapterDownloadAction(onPressed: onDownload, buttonKey: buttonKey),
    DownloadChapterState.failed => SeriesChapterDownloadAction(
        onPressed: onDownload,
        retryable: true,
        buttonKey: buttonKey,
      ),
    DownloadChapterState.queued ||
    DownloadChapterState.downloading ||
    DownloadChapterState.complete =>
      SeriesChapterDownloadAction(buttonKey: buttonKey),
  };
}
