import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/models/series_download_group.dart';

const hiddenFromQueue = {'completed', 'cancelled'};

const _statusRowPriority = {
  'downloading': 0,
  'queued': 1,
  'paused': 2,
  'failed': 3,
};

String seriesGroupKey(String source, String seriesId) => '$source::$seriesId';

List<SeriesDownloadGroup> groupDownloadsBySeries(List<DownloadItem> items) {
  final groups = <String, SeriesDownloadGroup>{};

  for (final item in items) {
    final key = seriesGroupKey(item.source, item.seriesId);
    final existing = groups[key];
    if (existing == null) {
      groups[key] = SeriesDownloadGroup(
        key: key,
        source: item.source,
        seriesId: item.seriesId,
        seriesTitle: item.seriesTitle,
        items: [item],
        active: item.isDownloading ? 1 : 0,
        queued: item.isQueued ? 1 : 0,
        completed: item.isCompleted ? 1 : 0,
        failed: item.isFailed ? 1 : 0,
        paused: item.isPaused ? 1 : 0,
      );
      continue;
    }

    groups[key] = SeriesDownloadGroup(
      key: existing.key,
      source: existing.source,
      seriesId: existing.seriesId,
      seriesTitle: existing.seriesTitle,
      items: [...existing.items, item],
      active: existing.active + (item.isDownloading ? 1 : 0),
      queued: existing.queued + (item.isQueued ? 1 : 0),
      completed: existing.completed + (item.isCompleted ? 1 : 0),
      failed: existing.failed + (item.isFailed ? 1 : 0),
      paused: existing.paused + (item.isPaused ? 1 : 0),
    );
  }

  final sorted = groups.values.toList()
    ..sort((a, b) {
      final aHasWork = a.active + a.queued > 0 ? 0 : 1;
      final bHasWork = b.active + b.queued > 0 ? 0 : 1;
      if (aHasWork != bHasWork) return aHasWork - bHasWork;
      return a.seriesTitle.compareTo(b.seriesTitle);
    });
  return sorted;
}

bool seriesCanPause(SeriesDownloadGroup group) => group.active + group.queued > 0;

bool seriesCanResume(SeriesDownloadGroup group) => group.paused > 0 || group.failed > 0;

bool seriesCanCancel(SeriesDownloadGroup group) =>
    group.items.any((item) => !item.isCompleted && !item.isCancelled);

List<DownloadItem> visibleGroupItems(SeriesDownloadGroup group) {
  return group.items
      .where((item) => !hiddenFromQueue.contains(item.status))
      .toList()
    ..sort((a, b) {
      final priorityA = _statusRowPriority[a.status] ?? 99;
      final priorityB = _statusRowPriority[b.status] ?? 99;
      return priorityA.compareTo(priorityB);
    });
}

bool matchesDownloadFilter(DownloadItem item, DownloadFilterTab filter) {
  if (hiddenFromQueue.contains(item.status)) return false;
  return switch (filter) {
    DownloadFilterTab.all => true,
    DownloadFilterTab.downloading => item.isDownloading,
    DownloadFilterTab.queued => item.isQueued,
    DownloadFilterTab.paused => item.isPaused,
    DownloadFilterTab.failed => item.isFailed,
  };
}

int downloadFilterCount(List<DownloadItem> items, DownloadFilterTab filter) =>
    items.where((item) => matchesDownloadFilter(item, filter)).length;

enum DownloadFilterTab { all, downloading, queued, paused, failed }

extension DownloadFilterTabLabel on DownloadFilterTab {
  String get label => switch (this) {
        DownloadFilterTab.all => 'All Active',
        DownloadFilterTab.downloading => 'Downloading',
        DownloadFilterTab.queued => 'Queued',
        DownloadFilterTab.paused => 'Paused',
        DownloadFilterTab.failed => 'Error',
      };
}
