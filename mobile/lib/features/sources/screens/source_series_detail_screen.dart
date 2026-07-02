import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/providers/downloads_provider.dart';
import 'package:aistudio_mobile/features/downloads/utils/queue_download_feedback.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/providers/sources_provider.dart';
import 'package:aistudio_mobile/features/sources/utils/chapter_label.dart';
import 'package:aistudio_mobile/features/updates/providers/updates_provider.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SourceSeriesDetailScreen extends ConsumerWidget {
  const SourceSeriesDetailScreen({
    super.key,
    required this.sourceId,
    required this.seriesId,
  });

  final String sourceId;
  final String seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(
      sourceSeriesDetailProvider((sourceId: sourceId, seriesId: seriesId)),
    );

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.sourceBrowse(sourceId)),
        ),
        title: const Text('Source Series'),
      ),
      body: detailAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load series.',
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(
                  sourceSeriesDetailProvider((sourceId: sourceId, seriesId: seriesId)),
                ),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) => _SeriesDetailBody(
          sourceId: sourceId,
          seriesId: seriesId,
          series: data.series,
          chapters: data.chapters,
        ),
      ),
    );
  }
}

class _SeriesDetailBody extends ConsumerStatefulWidget {
  const _SeriesDetailBody({
    required this.sourceId,
    required this.seriesId,
    required this.series,
    required this.chapters,
  });

  final String sourceId;
  final String seriesId;
  final SourceSeriesSummary series;
  final List<SourceChapterSummary> chapters;

  @override
  ConsumerState<_SeriesDetailBody> createState() => _SeriesDetailBodyState();
}

class _SeriesDetailBodyState extends ConsumerState<_SeriesDetailBody> {
  final Set<String> _selectedChapterIds = {};
  bool _downloadPending = false;

  void _toggleChapter(String chapterId) {
    setState(() {
      if (_selectedChapterIds.contains(chapterId)) {
        _selectedChapterIds.remove(chapterId);
      } else {
        _selectedChapterIds.add(chapterId);
      }
    });
  }

  void _showQueueFeedback(QueueDownloadResponse response) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(queueDownloadFeedbackMessage(response)),
        action: SnackBarAction(
          label: 'Downloads',
          onPressed: () => context.go(Routes.downloads),
        ),
      ),
    );
  }

  Future<void> _queueChapters(List<String> chapterIds) async {
    if (chapterIds.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Select at least one chapter.')),
      );
      return;
    }
    if (_downloadPending) return;

    setState(() => _downloadPending = true);
    try {
      final result = await ref.read(downloadsProvider.notifier).queueChapters(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            chapterIds: chapterIds,
            seriesTitle: widget.series.title,
          );
      if (!mounted) return;
      if (result.isErr) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result.error.userMessage)),
        );
        return;
      }
      setState(() {
        _selectedChapterIds.removeAll(chapterIds);
      });
      _showQueueFeedback(result.value);
    } finally {
      if (mounted) {
        setState(() => _downloadPending = false);
      }
    }
  }

  Future<void> _downloadSeries() async {
    if (_downloadPending || widget.chapters.isEmpty) return;

    setState(() => _downloadPending = true);
    try {
      final result = await ref.read(downloadsProvider.notifier).queueSeries(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
          );
      if (!mounted) return;
      if (result.isErr) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result.error.userMessage)),
        );
        return;
      }
      _showQueueFeedback(result.value);
    } finally {
      if (mounted) {
        setState(() => _downloadPending = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final series = widget.series;
    final chapters = widget.chapters;
    final downloadBusy = _downloadPending;

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: AspectRatio(
            aspectRatio: 2 / 3,
            child: Image.network(
              series.coverUrl,
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const ColoredBox(color: AppColors.panel),
            ),
          ),
        ),
        const SizedBox(height: AppSpacing.xl2),
        Text(series.title, style: AppTypography.displayMd),
        if (series.author != null) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(series.author!, style: AppTypography.body.copyWith(color: AppColors.muted)),
        ],
        if (series.description != null && series.description!.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          Text(series.description!, style: AppTypography.body),
        ],
        const SizedBox(height: AppSpacing.lg),
        _FollowButton(
          sourceId: widget.sourceId,
          seriesId: widget.seriesId,
          seriesTitle: series.title,
        ),
        const SizedBox(height: AppSpacing.lg),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            OutlinedButton.icon(
              key: const Key('download-series'),
              onPressed: downloadBusy || chapters.isEmpty ? null : _downloadSeries,
              icon: const Icon(Icons.download_outlined),
              label: const Text('Download Series'),
            ),
            OutlinedButton.icon(
              key: const Key('download-selected'),
              onPressed: downloadBusy || _selectedChapterIds.isEmpty
                  ? null
                  : () => _queueChapters(_selectedChapterIds.toList()),
              icon: const Icon(Icons.playlist_add_check_outlined),
              label: const Text('Download Selected'),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.xl2),
        Text('Chapters', style: AppTypography.h3),
        const SizedBox(height: AppSpacing.md),
        if (chapters.isEmpty)
          const EmptyState(
            icon: Icons.menu_book_outlined,
            message: 'No chapters available',
            subtitle: 'This source did not return any chapters for this series.',
          )
        else
          ...chapters.map(
            (chapter) {
              final label = chapterLabel(
                number: chapter.number,
                title: chapter.title,
              );
              final selected = _selectedChapterIds.contains(chapter.id);
              return Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: GlassCard(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Checkbox(
                        key: Key('select-${chapter.id}'),
                        value: selected,
                        onChanged: downloadBusy
                            ? null
                            : (_) => _toggleChapter(chapter.id),
                      ),
                      Expanded(
                        child: InkWell(
                          onTap: () => context.go(
                            RoutePaths.sourceReader(
                              widget.sourceId,
                              widget.seriesId,
                              chapter.id,
                            ),
                          ),
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(label.primary, style: AppTypography.labelLg),
                                if (label.secondary != null)
                                  Text(label.secondary!, style: AppTypography.bodySm),
                                Text(
                                  '${chapter.pageCount} pages',
                                  style: AppTypography.caption.copyWith(color: AppColors.muted),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      IconButton(
                        key: Key('download-${chapter.id}'),
                        tooltip: 'Download Chapter',
                        onPressed: downloadBusy
                            ? null
                            : () => _queueChapters([chapter.id]),
                        icon: const Icon(Icons.download_outlined),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
      ],
    );
  }
}

/// Follow / Unfollow button for the currently-viewed source series.
///
/// Reads follow state from [updatesProvider] (the shared trackers cache) via
/// [UpdatesNotifier.trackerFor] -- the single lookup implementation, not
/// duplicated here. This widget is the only part of the screen that watches
/// [updatesProvider], so tracker/notification changes elsewhere never rebuild
/// the rest of [SourceSeriesDetailScreen]. The button is disabled while a
/// follow or unfollow action is in flight (`actionPending`) or while the
/// trackers list has not yet loaded (so we never show a stale "Follow" label
/// for a series the user is already following).
class _FollowButton extends ConsumerWidget {
  const _FollowButton({
    required this.sourceId,
    required this.seriesId,
    required this.seriesTitle,
  });

  final String sourceId;
  final String seriesId;
  final String seriesTitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final updatesAsync = ref.watch(updatesProvider);
    final state = updatesAsync.valueOrNull;
    final loading = updatesAsync.isLoading;
    final actionPending = state?.actionPending ?? false;

    // While the trackers list is loading for the first time we cannot know
    // whether this series is followed, so keep the button disabled to avoid
    // a misleading label.
    final tracker = ref
        .read(updatesProvider.notifier)
        .trackerFor(source: sourceId, seriesId: seriesId);
    final isFollowed = tracker != null;
    final busy = actionPending || (loading && state == null);

    String label;
    if (busy) {
      label = isFollowed ? 'Unfollowing…' : 'Following…';
    } else {
      label = isFollowed ? 'Unfollow' : 'Follow';
    }

    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: busy ? null : () => _toggle(ref, isFollowed, tracker?.id),
        icon: isFollowed
            ? const Icon(Icons.notifications_off_outlined)
            : const Icon(Icons.notifications_active_outlined),
        label: Text(label),
      ),
    );
  }

  Future<void> _toggle(WidgetRef ref, bool isFollowed, int? trackerId) async {
    final notifier = ref.read(updatesProvider.notifier);
    if (isFollowed && trackerId != null) {
      await notifier.deleteTracker(trackerId);
    } else {
      await notifier.followSeries(
        source: sourceId,
        seriesId: seriesId,
        seriesTitle: seriesTitle,
      );
    }
  }
}
