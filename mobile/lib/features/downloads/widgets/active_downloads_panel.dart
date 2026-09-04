import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/active_download_queue_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloaded_series_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/storage_settings_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_copy.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// What the queue is doing, right now, in words the owner can act on.
///
/// This panel exists because of a specific failure: a series download was
/// started and there was no way to tell it was happening, let alone why it
/// might have stopped. So everything here is deliberately concrete — the
/// chapter being fetched, the page within it, how much of the series is on
/// the phone, and, when nothing is moving, *which* of the four things that
/// can hold the queue is holding it.
///
/// Renders nothing at all when there is no unfinished work and no blocking
/// pause: an always-present "idle" box would just be noise above the library.
class ActiveDownloadsPanel extends ConsumerWidget {
  const ActiveDownloadsPanel({
    super.key,
    required this.expanded,
    required this.onToggleExpanded,
    required this.onOpenStorageSettings,
  });

  /// Whether the per-chapter queue list below this panel is showing — owned
  /// by the screen, because that list is a sibling sliver (kept lazy rather
  /// than nested inside this card, so a 200-chapter queue costs nothing).
  final bool expanded;
  final VoidCallback onToggleExpanded;

  /// Jumps to the Storage tab — the "raise the cap / free up space" answer to
  /// a cap pause, one tap away instead of buried in Settings.
  final VoidCallback onOpenStorageSettings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queue = ref.watch(downloadQueueControllerProvider);
    final pending = ref.watch(activeDownloadQueueProvider).valueOrNull ??
        const <SavedChapter>[];

    if (pending.isEmpty && !queue.isBlocked) return const SizedBox.shrink();

    final current = pending
        .firstWhereOrNull((chapter) => chapter.identity == queue.currentChapter);
    final failedCount = pending
        .where((c) => c.state == DownloadChapterState.failed)
        .length;
    final waiting = pending.length - failedCount;

    return GlassCard(
      padding: const EdgeInsets.all(AppSpacing.lg),
      glowColor: queue.isBlocked ? AppColors.warning : AppColors.primary,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _HeaderRow(queue: queue, hasPending: pending.isNotEmpty),
          if (current != null) ...[
            const SizedBox(height: AppSpacing.md),
            _CurrentChapterProgress(chapter: current, queue: queue),
          ],
          if (queue.isBlocked) ...[
            const SizedBox(height: AppSpacing.md),
            _PauseReasonNotice(
              queue: queue,
              onOpenStorageSettings: onOpenStorageSettings,
            ),
          ],
          if (pending.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.md),
            _QueueSummaryRow(
              waiting: waiting,
              failedCount: failedCount,
              expanded: expanded,
              onToggleExpanded: onToggleExpanded,
            ),
          ],
          const SizedBox(height: AppSpacing.sm),
          Text(
            kForegroundOnlyDownloadsNote,
            style: AppTypography.caption.copyWith(color: AppColors.muted),
          ),
        ],
      ),
    );
  }
}

class _HeaderRow extends ConsumerWidget {
  const _HeaderRow({required this.queue, required this.hasPending});

  final DownloadQueueState queue;
  final bool hasPending;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final paused = queue.isBlocked;
    final userPaused =
        queue.pauseReason == DownloadQueuePauseReason.userPaused;

    return Row(
      children: [
        Icon(
          paused ? Icons.pause_circle_outline : Icons.downloading_outlined,
          color: paused ? AppColors.warning : AppColors.primary,
          size: 20,
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Text(
            paused
                ? 'Paused'
                : queue.isDownloading
                    ? 'Downloading'
                    : 'Waiting to start',
            style: AppTypography.h4,
          ),
        ),
        if (hasPending)
          IconButton(
            key: const Key('queue-pause-toggle'),
            tooltip: userPaused ? 'Resume downloads' : 'Pause downloads',
            icon: Icon(
              userPaused ? Icons.play_arrow : Icons.pause,
              color: AppColors.fg,
              size: 20,
            ),
            onPressed: () {
              final controller =
                  ref.read(downloadQueueControllerProvider.notifier);
              if (userPaused) {
                controller.resume();
              } else {
                controller.pause();
              }
            },
          ),
        if (hasPending)
          IconButton(
            key: const Key('queue-cancel-all'),
            tooltip: 'Cancel all downloads',
            icon: const Icon(Icons.clear_all, color: AppColors.muted, size: 20),
            onPressed: () => _confirmCancelAll(context, ref),
          ),
      ],
    );
  }

  Future<void> _confirmCancelAll(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: AppColors.surfaceElevated,
        title: Text('Cancel all downloads?', style: AppTypography.h4),
        content: Text(
          'Everything still queued, downloading or failed is dropped. '
          'Chapters already finished stay on your phone.',
          style: AppTypography.bodySm.copyWith(color: AppColors.muted),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep them'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(
              'Cancel all',
              style: AppTypography.label.copyWith(color: AppColors.danger),
            ),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(downloadQueueControllerProvider.notifier).cancelAll();
  }
}

class _CurrentChapterProgress extends ConsumerWidget {
  const _CurrentChapterProgress({required this.chapter, required this.queue});

  final SavedChapter chapter;
  final DownloadQueueState queue;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label =
        chapterLabel(number: chapter.chapterNumber, title: chapter.title);
    // Indeterminate until the manifest lands: a "page 0 of 0" bar reads as a
    // stall, which is the exact confusion this panel exists to remove.
    final total = queue.pageTotal;
    final value = total > 0 ? (queue.pagesDone / total).clamp(0.0, 1.0) : null;
    final seriesName = (chapter.seriesTitle?.isNotEmpty ?? false)
        ? chapter.seriesTitle!
        : chapter.seriesKey;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          seriesName,
          style: AppTypography.labelLg,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: AppSpacing.xxs),
        Text(
          total > 0
              ? '${label.primary} · page ${queue.pagesDone} of $total'
              : '${label.primary} · reading chapter details…',
          style: AppTypography.bodySm.copyWith(color: AppColors.muted),
        ),
        const SizedBox(height: AppSpacing.sm),
        ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.xs),
          child: LinearProgressIndicator(
            key: const Key('current-chapter-progress'),
            value: value,
            minHeight: 6,
            backgroundColor: AppColors.fg.withAlpha(20),
            valueColor: const AlwaysStoppedAnimation(AppColors.primary),
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        _SeriesProgressLine(chapter: chapter),
      ],
    );
  }
}

/// "18 of 32 chapters on this phone" for the series being downloaded — the
/// overall-progress half of the answer, since a per-chapter bar alone says
/// nothing about a 200-chapter series download.
class _SeriesProgressLine extends ConsumerWidget {
  const _SeriesProgressLine({required this.chapter});

  final SavedChapter chapter;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final groups = ref.watch(downloadedSeriesProvider).valueOrNull;
    final group = groups?.firstWhereOrNull(
      (DownloadedSeriesGroup g) =>
          g.sourceId == chapter.sourceId && g.seriesKey == chapter.seriesKey,
    );
    if (group == null || group.chapters.length < 2) {
      return const SizedBox.shrink();
    }
    final done = group.chapters
        .where((c) => c.state == DownloadChapterState.complete)
        .length;
    return Text(
      '$done of ${group.chapters.length} chapters saved in this series',
      style: AppTypography.caption.copyWith(color: AppColors.muted),
    );
  }
}

class _PauseReasonNotice extends ConsumerWidget {
  const _PauseReasonNotice({
    required this.queue,
    required this.onOpenStorageSettings,
  });

  final DownloadQueueState queue;
  final VoidCallback onOpenStorageSettings;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cap = ref.watch(storageCapProvider);
    final message = downloadPauseMessage(queue.pauseReason, cap);
    if (message == null) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: AppColors.warning, size: 16),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                message,
                style: AppTypography.bodySm.copyWith(height: 1.4),
              ),
            ),
          ],
        ),
        if (queue.pauseReason == DownloadQueuePauseReason.cap) ...[
          const SizedBox(height: AppSpacing.sm),
          OutlinedButton(
            key: const Key('queue-open-storage-settings'),
            onPressed: onOpenStorageSettings,
            child: const Text('Storage settings'),
          ),
        ],
        if (queue.pauseReason == DownloadQueuePauseReason.userPaused) ...[
          const SizedBox(height: AppSpacing.sm),
          FilledButton.icon(
            key: const Key('queue-resume'),
            onPressed:
                ref.read(downloadQueueControllerProvider.notifier).resume,
            icon: const Icon(Icons.play_arrow, size: 18),
            label: const Text('Resume'),
          ),
        ],
      ],
    );
  }
}

class _QueueSummaryRow extends StatelessWidget {
  const _QueueSummaryRow({
    required this.waiting,
    required this.failedCount,
    required this.expanded,
    required this.onToggleExpanded,
  });

  final int waiting;
  final int failedCount;
  final bool expanded;
  final VoidCallback onToggleExpanded;

  @override
  Widget build(BuildContext context) {
    final parts = <String>[
      if (waiting > 0) '$waiting in the queue',
      if (failedCount > 0) '$failedCount failed',
    ];

    return Row(
      children: [
        Expanded(
          child: Text(
            parts.join(' · '),
            style: AppTypography.bodySm.copyWith(
              color: failedCount > 0 ? AppColors.danger : AppColors.muted,
            ),
          ),
        ),
        TextButton.icon(
          key: const Key('queue-toggle-list'),
          onPressed: onToggleExpanded,
          icon: Icon(expanded ? Icons.expand_less : Icons.expand_more, size: 18),
          label: Text(expanded ? 'Hide queue' : 'Show queue'),
        ),
      ],
    );
  }
}

/// One unfinished chapter in the expanded queue list: what it is, what it is
/// waiting on, and the two things a user can do about it.
class QueuedChapterRow extends ConsumerWidget {
  const QueuedChapterRow({super.key, required this.chapter});

  final SavedChapter chapter;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label =
        chapterLabel(number: chapter.chapterNumber, title: chapter.title);
    final seriesName = (chapter.seriesTitle?.isNotEmpty ?? false)
        ? chapter.seriesTitle!
        : chapter.seriesKey;
    final failed = chapter.state == DownloadChapterState.failed;

    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      leading: Icon(
        failed ? Icons.error_outline : Icons.schedule,
        size: 18,
        color: failed ? AppColors.danger : AppColors.muted,
      ),
      title: Text(
        '$seriesName · ${label.primary}',
        style: AppTypography.bodySm,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        switch (chapter.state) {
          DownloadChapterState.failed =>
            chapter.error == null ? 'Failed' : 'Failed — ${chapter.error}',
          DownloadChapterState.downloading => 'Downloading',
          DownloadChapterState.queued ||
          DownloadChapterState.complete =>
            'Waiting in the queue',
        },
        style: AppTypography.caption.copyWith(
          color: failed ? AppColors.danger : AppColors.muted,
        ),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (failed)
            IconButton(
              key: Key('retry-${chapter.rowId}'),
              tooltip: 'Retry',
              icon: const Icon(Icons.refresh, size: 20),
              onPressed: () => ref
                  .read(downloadQueueControllerProvider.notifier)
                  .retryChapter(chapter.identity),
            ),
          IconButton(
            key: Key('cancel-${chapter.rowId}'),
            tooltip: 'Remove from queue',
            icon: const Icon(Icons.close, size: 20),
            onPressed: () => ref
                .read(downloadQueueControllerProvider.notifier)
                .cancelChapter(chapter.identity),
          ),
        ],
      ),
    );
  }
}
