import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:flutter/material.dart';

/// Display phases shown in the downloads queue UI.
///
/// [verifying] and [importing] are derived while backend `status` is still
/// `downloading`, using existing page/progress fields — no new API statuses.
enum DownloadQueueDisplayStatus {
  queued,
  downloading,
  verifying,
  importing,
  completed,
  failed,
  paused,
}

class DownloadRowActions {
  const DownloadRowActions({
    required this.showPause,
    required this.showResume,
    required this.showRetry,
    required this.showCancel,
  });

  final bool showPause;
  final bool showResume;
  final bool showRetry;
  final bool showCancel;
}

DownloadQueueDisplayStatus downloadQueueDisplayStatus(DownloadItem item) {
  if (item.isCompleted) return DownloadQueueDisplayStatus.completed;
  if (item.isFailed) return DownloadQueueDisplayStatus.failed;
  if (item.isPaused) return DownloadQueueDisplayStatus.paused;
  if (item.isQueued) return DownloadQueueDisplayStatus.queued;

  if (item.isDownloading) {
    final total = item.pagesTotal;
    final done = item.pagesDone;
    if (total > 0 && done >= total) {
      return DownloadQueueDisplayStatus.importing;
    }
    if (total > 0 && done > 0 && done < total && item.progress >= 90) {
      return DownloadQueueDisplayStatus.verifying;
    }
    return DownloadQueueDisplayStatus.downloading;
  }

  return DownloadQueueDisplayStatus.downloading;
}

String downloadQueueDisplayStatusKey(DownloadItem item) =>
    downloadQueueDisplayStatus(item).name;

String downloadQueueStatusLabel(DownloadItem item) {
  return switch (downloadQueueDisplayStatus(item)) {
    DownloadQueueDisplayStatus.queued => 'Queued',
    DownloadQueueDisplayStatus.downloading => 'Downloading',
    DownloadQueueDisplayStatus.verifying => 'Verifying',
    DownloadQueueDisplayStatus.importing => 'Importing',
    DownloadQueueDisplayStatus.completed => 'Completed',
    DownloadQueueDisplayStatus.failed => 'Failed',
    DownloadQueueDisplayStatus.paused => 'Paused',
  };
}

Color downloadQueueStatusColor(DownloadItem item) {
  return switch (downloadQueueDisplayStatus(item)) {
    DownloadQueueDisplayStatus.downloading => AppColors.violet400,
    DownloadQueueDisplayStatus.verifying => AppColors.cyan400,
    DownloadQueueDisplayStatus.importing => AppColors.primary,
    DownloadQueueDisplayStatus.queued => AppColors.cyan400,
    DownloadQueueDisplayStatus.paused => AppColors.warning,
    DownloadQueueDisplayStatus.failed => AppColors.danger,
    DownloadQueueDisplayStatus.completed => AppColors.success,
  };
}

DownloadRowActions downloadRowActions(DownloadItem item) => DownloadRowActions(
      showPause: item.isDownloading || item.isQueued,
      showResume: item.isPaused,
      showRetry: item.isFailed,
      showCancel: !item.isCompleted && !item.isCancelled,
    );

Map<DownloadQueueDisplayStatus, int> countDownloadQueueStatuses(
  Iterable<DownloadItem> items,
) {
  final counts = {
    for (final status in DownloadQueueDisplayStatus.values) status: 0,
  };
  for (final item in items) {
    counts[downloadQueueDisplayStatus(item)] =
        counts[downloadQueueDisplayStatus(item)]! + 1;
  }
  return counts;
}
