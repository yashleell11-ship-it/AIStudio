import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// The queue as the user thinks of it: everything still owed to them —
/// queued, mid-download, or failed — oldest first.
///
/// Separate from [downloadedSeriesProvider] (which loads the whole on-device
/// library grouped by series) because this one is watched by the navigation
/// shell for the tab badge, i.e. all the time, on every screen. A narrow
/// indexed query over the handful of unfinished rows is the right cost for
/// that; re-reading every downloaded chapter would not be.
///
/// Re-queries on [DownloadQueueState.queueRevision] only — not on the
/// page-by-page counter — so a forty-page chapter costs it one refresh.
final activeDownloadQueueProvider =
    FutureProvider.autoDispose<List<SavedChapter>>((ref) async {
  final store = ref.watch(downloadsStoreProvider);
  ref.watch(downloadQueueControllerProvider.select((s) => s.queueRevision));
  if (store == null) return const [];
  return store.unfinishedChapters();
});

/// How many chapters are still owed. Drives the count badge on the Downloads
/// tab — the answer to "I tapped Download Series and nothing seemed to
/// happen", visible from every other tab without opening this one.
///
/// Resolves to 0 rather than throwing while the query is in flight or if it
/// fails: a badge is an ambient hint, and a broken one must never be the
/// thing that takes down the navigation bar.
final activeDownloadCountProvider = Provider.autoDispose<int>(
  (ref) => ref.watch(activeDownloadQueueProvider).valueOrNull?.length ?? 0,
  name: 'activeDownloadCount',
);
