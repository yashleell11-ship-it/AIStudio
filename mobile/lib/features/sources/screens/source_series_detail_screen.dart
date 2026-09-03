import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/chapter_download_action.dart';
import 'package:manhwamaniacs/features/downloads/widgets/download_series_button.dart';
import 'package:manhwamaniacs/features/sources/models/source_chapter_progress.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/features/updates/widgets/series_follow_button.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_body.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_chips.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_meta.dart';

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
    // Name the screen after the series the user tapped, not the generic route.
    final title = detailAsync.valueOrNull?.series.title;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(RoutePaths.sourceBrowse(sourceId)),
        ),
        title: Text(
          title == null || title.isEmpty ? 'Series' : title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
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
  SeriesChapterSortOrder _sortOrder = SeriesChapterSortOrder.newest;

  List<SourceChapterSummary> _sortedChapters(
    List<SourceChapterSummary> chapters,
    SeriesChapterSortOrder order,
  ) =>
      sortSeriesChapters(
        chapters,
        numberOf: (chapter) => chapter.number,
        order: order,
      );

  /// Newest chapter, for the header meta line. Prefers the highest-numbered
  /// chapter in the loaded list and falls back to the source-provided
  /// `latest_chapter` string. Null only when neither is available.
  String? _latestChapterLabel() {
    // The loaded list wins over the source's summary field. Connectors scrape
    // `latest_chapter` from a listing page that can lag the chapter list by
    // days, so preferring it let the header read "Latest: Ch. 118" directly
    // above a newest-first list whose top row was Chapter 120 -- the one number
    // on this screen that has to be right.
    final newest =
        _sortedChapters(widget.chapters, SeriesChapterSortOrder.newest).firstOrNull;
    if (newest != null) {
      return chapterLabel(number: newest.number, title: newest.title).primary;
    }
    final provided = widget.series.latestChapter?.trim();
    if (provided != null && provided.isNotEmpty) return provided;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final series = widget.series;
    final chapters = widget.chapters;
    final progressMap = ref.watch(sourceProgressProvider);
    final sortedChapters = _sortedChapters(chapters, _sortOrder);
    final latestRead = ref.read(sourceProgressProvider.notifier).latestForSeries(
          sourceId: widget.sourceId,
          seriesId: widget.seriesId,
        );

    return SeriesDetailBody(
      cover: series.coverUrl.isEmpty
          ? null
          : SeriesCoverImage(url: series.coverUrl, borderRadius: 0),
      title: series.title,
      author: series.author,
      artist: series.artist,
      metaLine: seriesDetailMetaLine(
        latestChapterLabel: _latestChapterLabel(),
        // The loaded chapter list is authoritative; the summary count is only a
        // fallback for sources that omit chapters from the detail payload.
        chapterCount:
            chapters.isNotEmpty ? chapters.length : series.chapterCount,
      ),
      description: series.description,
      primaryAction: chapters.isEmpty
          ? null
          : _ReadPrimaryButton(
              sourceId: widget.sourceId,
              seriesId: widget.seriesId,
              latestRead: latestRead,
              orderedChapters:
                  _sortedChapters(chapters, SeriesChapterSortOrder.oldest),
            ),
      followAction: SeriesFollowButton(
        key: const Key('follow-toggle'),
        sourceId: widget.sourceId,
        seriesKey: widget.seriesId,
      ),
      secondaryActions: [
        DownloadSeriesButton(
          chapters: [
            for (final chapter in chapters)
              (
                id: (
                  sourceId: widget.sourceId,
                  seriesKey: widget.seriesId,
                  chapterKey: chapter.id,
                ),
                chapterNumber: chapter.number,
                title: chapter.title,
                seriesTitle: series.title,
              ),
          ],
        ),
      ],
      details: [
        // Status and genres get the same pill treatment the library page gives
        // reading status and tags -- the source page simply had nowhere to put
        // them before.
        if ((series.status != null && series.status!.isNotEmpty) ||
            series.genres.isNotEmpty)
          SeriesDetailChipRow(
            chips: [
              if (series.status != null && series.status!.isNotEmpty)
                SeriesDetailChip(
                  label: series.status!.toUpperCase(),
                  color: AppColors.primary,
                ),
              for (final genre in series.genres) SeriesDetailChip(label: genre),
            ],
          ),
      ],
      sortOrder: _sortOrder,
      onSortOrderChanged: (order) => setState(() => _sortOrder = order),
      emptyChapters: const EmptyState(
        icon: Icons.menu_book_outlined,
        message: 'No chapters available',
        subtitle: 'This source did not return any chapters for this series.',
      ),
      chapterTiles: [
        for (final chapter in sortedChapters)
          _buildChapterTile(
            chapter: chapter,
            progressMap: progressMap,
            latestRead: latestRead,
          ),
      ],
    );
  }

  Widget _buildChapterTile({
    required SourceChapterSummary chapter,
    required Map<String, SourceChapterProgress> progressMap,
    required LatestSourceRead? latestRead,
  }) {
    final progress = progressMap[sourceProgressKey(
      sourceId: widget.sourceId,
      seriesId: widget.seriesId,
      chapterId: chapter.id,
    )];
    final completed = progress?.completed ?? false;
    // Prefer the page count captured while reading (authoritative for this
    // reader), falling back to the source-provided count.
    final storedCount = progress?.pageCount ?? 0;
    final effectiveCount = storedCount > 0 ? storedCount : chapter.pageCount;

    final downloadStatuses = ref
        .watch(
          seriesChapterDownloadStatusProvider(
            (sourceId: widget.sourceId, seriesKey: widget.seriesId),
          ),
        )
        .valueOrNull;

    return SeriesChapterTile(
      key: Key('chapter-${chapter.id}'),
      label: chapterLabel(number: chapter.number, title: chapter.title),
      progressText: seriesChapterProgressText(
        pageCount: effectiveCount,
        page: progress?.page,
        completed: completed,
      ),
      inProgress: progress != null && !completed,
      isRead: completed,
      // "Reading" marks the chapter Continue would resume -- the last one
      // opened, and only while it is unfinished.
      isCurrent: latestRead?.chapterId == chapter.id && !completed,
      onTap: () => context.go(
        RoutePaths.sourceReader(widget.sourceId, widget.seriesId, chapter.id),
      ),
      download: chapterDownloadAction(
        hasScope: ref.watch(activeDownloadsScopeIdProvider) != null,
        status: downloadStatuses?[chapter.id],
        buttonKey: Key('download-${chapter.id}'),
        onDownload: () => ref.read(downloadQueueControllerProvider.notifier).enqueueChapter(
              id: (
                sourceId: widget.sourceId,
                seriesKey: widget.seriesId,
                chapterKey: chapter.id,
              ),
              chapterNumber: chapter.number,
              title: chapter.title,
              seriesTitle: widget.series.title,
            ),
      ),
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
