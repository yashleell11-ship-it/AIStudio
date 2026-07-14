import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_provider.dart';
import 'package:manhwamaniacs/features/downloads/utils/queue_download_feedback.dart';
import 'package:manhwamaniacs/features/profiles/providers/profile_scope.dart';
import 'package:manhwamaniacs/features/sources/models/source_chapter_progress.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_series_download_status_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/features/sources/widgets/source_chapter_download_status_badge.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

/// Chapter list ordering. Defaults to newest-first (highest chapter number).
enum _ChapterSortOrder { newest, oldest }

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
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(RoutePaths.sourceBrowse(sourceId)),
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
  _ChapterSortOrder _sortOrder = _ChapterSortOrder.newest;

  /// Returns a sorted copy of [chapters] by chapter number, nulls always last.
  /// Newest = descending, oldest = ascending.
  List<SourceChapterSummary> _sortedChapters(
    List<SourceChapterSummary> chapters,
    _ChapterSortOrder order,
  ) {
    final copy = [...chapters];
    copy.sort((a, b) {
      final an = a.number;
      final bn = b.number;
      if (an == null && bn == null) return 0;
      if (an == null) return 1;
      if (bn == null) return -1;
      return order == _ChapterSortOrder.newest
          ? bn.compareTo(an)
          : an.compareTo(bn);
    });
    return copy;
  }

  /// Per-row progress line. Unread → "{n} pages"; reading → "{page}/{n} pages";
  /// done → "{n}/{n} pages". Returns null when the page count is unknown.
  String? _chapterProgressText(SourceChapterProgress? progress, int pageCount) {
    if (pageCount <= 0) return null;
    if (progress == null) return '$pageCount pages';
    if (progress.completed) return '$pageCount/$pageCount pages';
    return '${progress.page}/$pageCount pages';
  }

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
    showQueueDownloadSnackBar(context, response);
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
    final downloadLookup = ref.watch(
      sourceSeriesChapterDownloadLookupProvider(
        (sourceId: widget.sourceId, seriesId: widget.seriesId),
      ),
    );
    final progressMap = ref.watch(sourceProgressProvider);
    final sortedChapters = _sortedChapters(chapters, _sortOrder);
    final latestRead = ref.read(sourceProgressProvider.notifier).latestForSeries(
          sourceId: widget.sourceId,
          seriesId: widget.seriesId,
        );

    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl2 + MediaQuery.paddingOf(context).bottom,
      ),
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: AspectRatio(
            aspectRatio: 2 / 3,
            child: series.coverUrl.isEmpty
                ? const ColoredBox(color: AppColors.panel)
                : SeriesCoverImage(
                    url: series.coverUrl,
                    borderRadius: 0,
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
        if (chapters.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.lg),
          _ReadPrimaryButton(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            latestRead: latestRead,
            orderedChapters:
                _sortedChapters(chapters, _ChapterSortOrder.oldest),
          ),
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
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text('Chapters', style: AppTypography.h3),
            if (chapters.isNotEmpty)
              _SortToggle(
                value: _sortOrder,
                onChanged: (order) => setState(() => _sortOrder = order),
              ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        if (chapters.isEmpty)
          const EmptyState(
            icon: Icons.menu_book_outlined,
            message: 'No chapters available',
            subtitle: 'This source did not return any chapters for this series.',
          )
        else
          ...sortedChapters.map(
            (chapter) {
              final label = chapterLabel(
                number: chapter.number,
                title: chapter.title,
              );
              final selected = _selectedChapterIds.contains(chapter.id);
              final chapterStatus = downloadLookup.statusFor(chapter.id);
              final downloadDisabled =
                  downloadBusy || downloadLookup.isDownloadDisabled(chapter.id);
              final retryable = downloadLookup.isRetryable(chapter.id);
              final progress = progressMap[sourceProgressKey(
                sourceId: widget.sourceId,
                seriesId: widget.seriesId,
                chapterId: chapter.id,
              )];
              final completed = progress?.completed ?? false;
              // Prefer the page count captured while reading (authoritative for
              // this reader), falling back to the source-provided count.
              final storedCount = progress?.pageCount ?? 0;
              final effectiveCount =
                  storedCount > 0 ? storedCount : chapter.pageCount;
              final progressText =
                  _chapterProgressText(progress, effectiveCount);
              final titleColor = completed ? AppColors.muted : null;
              final card = Padding(
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
                                Text(
                                  label.primary,
                                  style: AppTypography.labelLg
                                      .copyWith(color: titleColor),
                                ),
                                if (label.secondary != null)
                                  Text(label.secondary!, style: AppTypography.bodySm),
                                if (progressText != null)
                                  Text(
                                    progressText,
                                    style: AppTypography.caption.copyWith(
                                      // In-progress reads glow warm amber;
                                      // unread/completed stay muted.
                                      color: (progress != null && !completed)
                                          ? AppColors.primary
                                          : AppColors.muted,
                                    ),
                                  ),
                                SourceChapterDownloadStatusBadge(
                                  key: Key('chapter-status-${chapter.id}'),
                                  status: chapterStatus,
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),
                      IconButton(
                        key: Key('download-${chapter.id}'),
                        tooltip: retryable ? 'Retry Download' : 'Download Chapter',
                        onPressed: downloadDisabled
                            ? null
                            : () => _queueChapters([chapter.id]),
                        icon: Icon(
                          retryable ? Icons.refresh : Icons.download_outlined,
                        ),
                      ),
                    ],
                  ),
                ),
              );
              // Read chapters recede: dropping the whole card's opacity over the
              // dark background reads as a darker, muted "already read" row.
              return completed ? Opacity(opacity: 0.6, child: card) : card;
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
        onPressed:
            busy ? null : () => _toggle(context, ref, isFollowed, tracker?.id),
        icon: isFollowed
            ? const Icon(Icons.notifications_off_outlined)
            : const Icon(Icons.notifications_active_outlined),
        label: Text(label),
      ),
    );
  }

  Future<void> _toggle(
    BuildContext context,
    WidgetRef ref,
    bool isFollowed,
    int? trackerId,
  ) async {
    final messenger = ScaffoldMessenger.of(context);
    final notifier = ref.read(updatesProvider.notifier);
    final AppError? error;
    if (isFollowed && trackerId != null) {
      error = await notifier.deleteTracker(trackerId);
    } else {
      error = await notifier.followSeries(
        source: sourceId,
        seriesId: seriesId,
        seriesTitle: seriesTitle,
      );
    }
    if (error == null) {
      // The trackers cache was refreshed by the action, so the button label
      // already reflects the new followed state; confirm it to the user.
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            isFollowed
                ? 'Unfollowed'
                : 'Following — you\'ll be notified of new chapters',
          ),
        ),
      );
      return;
    }
    // A per-profile guard rejection hands off to the picker instead of a raw
    // error; anything else surfaces inline.
    if (recoverFromProfileScopeError(ref, error)) return;
    messenger.showSnackBar(
      SnackBar(content: Text(error.userMessage)),
    );
  }
}

/// Primary read CTA. "Continue" when there is progress — resuming the
/// latest-read chapter at its saved page while it is still in progress, or
/// advancing to the next chapter at page 1 once that chapter is finished —
/// otherwise "Read Online" from the earliest chapter at page 1.
class _ReadPrimaryButton extends StatelessWidget {
  const _ReadPrimaryButton({
    required this.sourceId,
    required this.seriesId,
    required this.latestRead,
    required this.orderedChapters,
  });

  final String sourceId;
  final String seriesId;
  final LatestSourceRead? latestRead;

  /// Chapters in reading order (nulls-last ascending) — same comparator used
  /// for the earliest-chapter / auto-queue-next logic. Never empty (the button
  /// is only shown when the series has chapters).
  final List<SourceChapterSummary> orderedChapters;

  @override
  Widget build(BuildContext context) {
    final resume = latestRead;
    final String target;
    if (resume != null) {
      final index =
          orderedChapters.indexWhere((c) => c.id == resume.chapterId);
      final nextChapter = resume.progress.completed &&
              index != -1 &&
              index + 1 < orderedChapters.length
          ? orderedChapters[index + 1]
          : null;
      if (nextChapter != null) {
        // The latest-read chapter is finished — advance to the next unread
        // chapter at page 1 instead of reopening the completed one.
        target = RoutePaths.sourceReader(sourceId, seriesId, nextChapter.id);
      } else {
        // Still mid-chapter (or nothing after a finished last chapter) —
        // resume in place at the saved page.
        final path =
            RoutePaths.sourceReader(sourceId, seriesId, resume.chapterId);
        target = '$path?page=${resume.progress.page}';
      }
    } else {
      target =
          RoutePaths.sourceReader(sourceId, seriesId, orderedChapters.first.id);
    }
    final isContinue = resume != null;

    return PrimaryPillButton(
      key: const Key('read-primary'),
      expanded: true,
      onPressed: () => context.go(target),
      icon: isContinue ? Icons.play_arrow_rounded : Icons.menu_book_outlined,
      label: isContinue ? 'Continue' : 'Read Online',
    );
  }
}

/// Compact Newest/Oldest segmented toggle for the chapter list header.
class _SortToggle extends StatelessWidget {
  const _SortToggle({required this.value, required this.onChanged});

  final _ChapterSortOrder value;
  final ValueChanged<_ChapterSortOrder> onChanged;

  @override
  Widget build(BuildContext context) {
    final motion = MediaQuery.disableAnimationsOf(context)
        ? Duration.zero
        : const Duration(milliseconds: 150);
    return Container(
      padding: const EdgeInsets.all(2),
      decoration: BoxDecoration(
        color: AppColors.surface2,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.glassEdge),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _segment('Newest', _ChapterSortOrder.newest, motion),
          _segment('Oldest', _ChapterSortOrder.oldest, motion),
        ],
      ),
    );
  }

  Widget _segment(String label, _ChapterSortOrder order, Duration motion) {
    final selected = value == order;
    return GestureDetector(
      onTap: selected ? null : () => onChanged(order),
      child: AnimatedContainer(
        duration: motion,
        curve: Curves.easeOut,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : Colors.transparent,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Text(
          label,
          style: AppTypography.caption.copyWith(
            color: selected ? AppColors.primaryFg : AppColors.muted,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
          ),
        ),
      ),
    );
  }
}