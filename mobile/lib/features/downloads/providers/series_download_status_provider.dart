import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// One chapter's on-device download state, for driving a
/// [SeriesChapterDownloadAction] — the enabled/disabled/retryable icon on a
/// chapter row.
typedef ChapterDownloadStatus = ({DownloadChapterState state, String? error});

/// Every chapter of [series] that has a row in the active scope's store,
/// keyed by chapter key. A chapter with no entry here has never been queued
/// — the "not yet downloaded" default a chapter tile's download button
/// starts from.
///
/// Re-fetches whenever a chapter row's state changes (queued, finished,
/// failed, cancelled) so a download button's icon updates without the screen
/// needing its own polling.
/// Resolves to an empty map with no active scope — no store, no statuses,
/// matching "no scope → UI shows nothing downloaded".
final seriesChapterDownloadStatusProvider = FutureProvider.autoDispose
    .family<Map<String, ChapterDownloadStatus>, SeriesIdentity>((ref, series) async {
  final store = ref.watch(downloadsStoreProvider);
  // Dependency only, to force a re-fetch whenever a row's state changes.
  ref.watch(downloadQueueControllerProvider.select((s) => s.queueRevision));
  if (store == null) return const {};

  final chapters = await store.listChapters();
  return {
    for (final chapter in chapters)
      if (chapter.sourceId == series.sourceId && chapter.seriesKey == series.seriesKey)
        chapter.chapterKey: (state: chapter.state, error: chapter.error),
  };
});
