import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:flutter/material.dart';

enum SourceChapterDownloadUiStatus {
  none,
  queued,
  downloading,
  completed,
  failed,
}

class SourceChapterDownloadLookup {
  const SourceChapterDownloadLookup({required this.statusByChapterId});

  const SourceChapterDownloadLookup.empty() : statusByChapterId = const {};

  final Map<String, SourceChapterDownloadUiStatus> statusByChapterId;

  SourceChapterDownloadUiStatus statusFor(String chapterId) =>
      statusByChapterId[chapterId] ?? SourceChapterDownloadUiStatus.none;

  bool showsStatusBadge(String chapterId) =>
      statusFor(chapterId) != SourceChapterDownloadUiStatus.none;

  bool isDownloadDisabled(String chapterId) {
    return switch (statusFor(chapterId)) {
      SourceChapterDownloadUiStatus.queued ||
      SourceChapterDownloadUiStatus.downloading ||
      SourceChapterDownloadUiStatus.completed =>
        true,
      SourceChapterDownloadUiStatus.none ||
      SourceChapterDownloadUiStatus.failed =>
        false,
    };
  }

  bool isRetryable(String chapterId) =>
      statusFor(chapterId) == SourceChapterDownloadUiStatus.failed;
}

SourceChapterDownloadLookup buildSourceChapterDownloadLookup({
  required String sourceId,
  required String seriesId,
  required List<DownloadItem> items,
}) {
  final latestByChapter = <String, DownloadItem>{};

  for (final item in items) {
    if (item.source != sourceId || item.seriesId != seriesId) continue;
    if (item.isCancelled) continue;

    final existing = latestByChapter[item.chapterId];
    if (existing == null || item.updatedAt.isAfter(existing.updatedAt)) {
      latestByChapter[item.chapterId] = item;
    }
  }

  return SourceChapterDownloadLookup(
    statusByChapterId: {
      for (final entry in latestByChapter.entries)
        entry.key: uiStatusFromDownloadItem(entry.value),
    },
  );
}

SourceChapterDownloadUiStatus uiStatusFromDownloadItem(DownloadItem item) {
  if (item.isCompleted) return SourceChapterDownloadUiStatus.completed;
  if (item.isFailed) return SourceChapterDownloadUiStatus.failed;
  if (item.isDownloading) return SourceChapterDownloadUiStatus.downloading;
  if (item.isQueued || item.isPaused) return SourceChapterDownloadUiStatus.queued;
  return SourceChapterDownloadUiStatus.none;
}

String sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus status) {
  return switch (status) {
    SourceChapterDownloadUiStatus.none => 'Download',
    SourceChapterDownloadUiStatus.queued => 'Queued',
    SourceChapterDownloadUiStatus.downloading => 'Downloading',
    SourceChapterDownloadUiStatus.completed => 'Completed',
    SourceChapterDownloadUiStatus.failed => 'Failed',
  };
}

Color sourceChapterDownloadStatusColor(SourceChapterDownloadUiStatus status) {
  return switch (status) {
    SourceChapterDownloadUiStatus.downloading => AppColors.violet400,
    SourceChapterDownloadUiStatus.queued => AppColors.cyan400,
    SourceChapterDownloadUiStatus.completed => AppColors.success,
    SourceChapterDownloadUiStatus.failed => AppColors.danger,
    SourceChapterDownloadUiStatus.none => AppColors.muted,
  };
}
