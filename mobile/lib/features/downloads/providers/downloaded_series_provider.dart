import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';

/// Every downloaded/downloading/queued/failed chapter in the active scope,
/// grouped by series — the Downloads screen's data source. Empty with no
/// active scope (no store, no listing — the isolation contract). Re-fetches
/// whenever the download queue's state changes so a chapter finishing or
/// failing is reflected without the screen polling.
final downloadedSeriesProvider =
    FutureProvider.autoDispose<List<DownloadedSeriesGroup>>((ref) async {
  final store = ref.watch(downloadsStoreProvider);
  ref.watch(downloadQueueControllerProvider);
  if (store == null) return const [];

  final chapters = await store.listChapters();
  final bySeries = <String, List<SavedChapter>>{};
  final order = <String>[];
  for (final chapter in chapters) {
    final key = '${chapter.sourceId} ${chapter.seriesKey}';
    final group = bySeries.putIfAbsent(key, () {
      order.add(key);
      return [];
    });
    group.add(chapter);
  }

  return [
    for (final key in order)
      DownloadedSeriesGroup(
        sourceId: bySeries[key]!.first.sourceId,
        seriesKey: bySeries[key]!.first.seriesKey,
        seriesTitle: bySeries[key]!
            .map((c) => c.seriesTitle)
            .firstWhere((t) => t != null && t.isNotEmpty, orElse: () => null),
        chapters: bySeries[key]!,
      ),
  ];
});
