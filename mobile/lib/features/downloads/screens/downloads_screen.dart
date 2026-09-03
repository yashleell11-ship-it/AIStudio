import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/downloaded_series_group.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloaded_series_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/downloads_storage_card.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';

/// Every chapter with an on-device footprint, grouped by series — spec §3's
/// "Downloads tab": real sizes, pin toggles, per-chapter remove, and the
/// queue's own status (a plain badge, since the download button on a series
/// page already shows the enabled/disabled/retryable affordance).
class DownloadsScreen extends ConsumerWidget {
  const DownloadsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scopeId = ref.watch(activeDownloadsScopeIdProvider);
    final groupsAsync = ref.watch(downloadedSeriesProvider);
    final queueState = ref.watch(downloadQueueControllerProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () => context.pop(),
        ),
        title: const Text('Downloads'),
      ),
      body: scopeId == null
          ? const EmptyState(
              icon: Icons.person_outline,
              message: 'No active profile',
              subtitle: 'Choose a reading profile to see its downloads.',
            )
          : Column(
              children: [
                _QueueStatusBanner(state: queueState),
                Expanded(
                  child: groupsAsync.when(
                    loading: () => const Center(child: CircularProgressIndicator()),
                    error: (error, _) => Center(
                      child: Text(
                        'Could not load downloads.',
                        style: AppTypography.body.copyWith(color: AppColors.danger),
                      ),
                    ),
                    data: (groups) {
                      if (groups.isEmpty) {
                        return const EmptyState(
                          icon: Icons.download_outlined,
                          message: 'No downloads yet',
                          subtitle:
                              'Chapters you download for offline reading show up here.',
                        );
                      }
                      return ListView(
                        padding: EdgeInsets.fromLTRB(
                          AppSpacing.xl2,
                          AppSpacing.lg,
                          AppSpacing.xl2,
                          AppSpacing.xl2 + MediaQuery.paddingOf(context).bottom,
                        ),
                        children: [
                          for (final group in groups)
                            Padding(
                              padding: const EdgeInsets.only(bottom: AppSpacing.md),
                              child: _SeriesDownloadCard(group: group),
                            ),
                        ],
                      );
                    },
                  ),
                ),
              ],
            ),
    );
  }
}

class _QueueStatusBanner extends StatelessWidget {
  const _QueueStatusBanner({required this.state});

  final DownloadQueueState state;

  String? get _message => switch (state.pauseReason) {
        DownloadQueuePauseReason.backgrounded =>
          'Downloads pause while the app is in the background — keep it open '
              'to keep downloading.',
        DownloadQueuePauseReason.freeSpaceFloor =>
          'Paused: your phone is nearly full. Free up space to resume.',
        DownloadQueuePauseReason.cap =>
          'Paused: you\'ve reached your storage cap. Raise it or free up '
              'space in Settings → Storage to resume.',
        DownloadQueuePauseReason.noScope || DownloadQueuePauseReason.none => null,
      };

  @override
  Widget build(BuildContext context) {
    final message = _message;
    if (message == null && !state.isDownloading) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        AppSpacing.lg,
        AppSpacing.xl2,
        0,
      ),
      child: GlassCard(
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Row(
          children: [
            Icon(
              message != null ? Icons.pause_circle_outline : Icons.downloading_outlined,
              color: message != null ? AppColors.warning : AppColors.primary,
              size: 20,
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                message ?? 'Downloading…',
                style: AppTypography.bodySm,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SeriesDownloadCard extends ConsumerStatefulWidget {
  const _SeriesDownloadCard({required this.group});

  final DownloadedSeriesGroup group;

  @override
  ConsumerState<_SeriesDownloadCard> createState() => _SeriesDownloadCardState();
}

class _SeriesDownloadCardState extends ConsumerState<_SeriesDownloadCard> {
  var _expanded = false;

  @override
  Widget build(BuildContext context) {
    final group = widget.group;

    return GlassCard(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          (group.seriesTitle?.isNotEmpty ?? false)
                              ? group.seriesTitle!
                              : group.seriesKey,
                          style: AppTypography.labelLg,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        const SizedBox(height: AppSpacing.xxs),
                        Text(
                          '${group.chapters.length} chapter'
                          '${group.chapters.length == 1 ? '' : 's'} · '
                          '${formatDownloadBytes(group.totalBytes)}',
                          style: AppTypography.caption.copyWith(color: AppColors.muted),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: Key('pin-series-${group.sourceId}-${group.seriesKey}'),
                    tooltip: group.pinned ? 'Unpin series' : 'Pin series',
                    icon: Icon(
                      group.pinned ? Icons.push_pin : Icons.push_pin_outlined,
                      color: group.pinned ? AppColors.primary : AppColors.muted,
                    ),
                    onPressed: () => _togglePin(group),
                  ),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    color: AppColors.muted,
                  ),
                ],
              ),
            ),
          ),
          if (_expanded)
            for (final chapter in group.chapters)
              _ChapterRow(
                chapter: chapter,
                onRemoved: () => ref.invalidate(downloadedSeriesProvider),
              ),
          if (_expanded) const SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  Future<void> _togglePin(DownloadedSeriesGroup group) async {
    await ref.read(downloadsStoreProvider)?.setSeriesPinned(
          series: (sourceId: group.sourceId, seriesKey: group.seriesKey),
          pinned: !group.pinned,
        );
    ref.invalidate(downloadedSeriesProvider);
  }
}

class _ChapterRow extends ConsumerWidget {
  const _ChapterRow({required this.chapter, required this.onRemoved});

  final SavedChapter chapter;
  final VoidCallback onRemoved;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final label = chapterLabel(number: chapter.chapterNumber, title: chapter.title);

    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
      title: Text(label.primary, style: AppTypography.bodySm),
      subtitle: Text(
        '${_stateLabel(chapter.state, chapter.error)} · '
        '${formatDownloadBytes(chapter.bytes)}',
        style: AppTypography.caption.copyWith(color: AppColors.muted),
      ),
      onTap: chapter.state == DownloadChapterState.complete
          ? () => context.push(
                RoutePaths.reader(chapter.sourceId, chapter.seriesKey, chapter.chapterKey),
              )
          : null,
      trailing: IconButton(
        key: Key('remove-${chapter.sourceId}-${chapter.seriesKey}-${chapter.chapterKey}'),
        tooltip: 'Remove download',
        icon: const Icon(Icons.delete_outline, size: 20),
        onPressed: () => _remove(ref),
      ),
    );
  }

  String _stateLabel(DownloadChapterState state, String? error) => switch (state) {
        DownloadChapterState.queued => 'Queued',
        DownloadChapterState.downloading => 'Downloading…',
        DownloadChapterState.complete => 'Downloaded',
        DownloadChapterState.failed => error == null ? 'Failed' : 'Failed — $error',
      };

  Future<void> _remove(WidgetRef ref) async {
    await ref.read(downloadsStoreProvider)?.deleteDownload(
          (
            sourceId: chapter.sourceId,
            seriesKey: chapter.seriesKey,
            chapterKey: chapter.chapterKey,
          ),
        );
    onRemoved();
  }
}
