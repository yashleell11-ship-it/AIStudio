import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/chapter_download_action.dart';
import 'package:manhwamaniacs/features/downloads/widgets/download_series_button.dart';
import 'package:manhwamaniacs/features/novels/models/novel_typography.dart';
import 'package:manhwamaniacs/features/novels/providers/novel_series_providers.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/features/sources/models/source_chapter_progress.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/updates/widgets/series_follow_button.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';

/// A book's front matter and its Contents.
///
/// Deliberately not the manga series screen with a different font. The manga
/// screen is poster-led: a full-bleed cover carries the identity and the
/// metadata is a caption under it. Novels have weak cover art — an
/// aggregator's generated placeholder more often than not — and strong
/// metadata, so this inverts it: the title is the largest thing on the page,
/// set in the serif that carries the whole mode, with the byline under it and
/// the cover kept small and subordinate beside them. When there IS real art it
/// still aids recognition, which is why it is kept rather than dropped.
///
/// The chapter list is a **table of contents**, not a download queue: the
/// number sits in its own column and the title beside it, once (see
/// [tocEntry]), and the second line is length — words and an estimated reading
/// time — because a novel chapter has no page count worth showing.
class NovelSeriesDetailView extends ConsumerStatefulWidget {
  const NovelSeriesDetailView({
    super.key,
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
  ConsumerState<NovelSeriesDetailView> createState() =>
      _NovelSeriesDetailViewState();
}

class _NovelSeriesDetailViewState extends ConsumerState<NovelSeriesDetailView> {
  SeriesChapterSortOrder _sortOrder = SeriesChapterSortOrder.oldest;

  @override
  Widget build(BuildContext context) {
    final series = widget.series;
    final colors = context.colors;
    final identity = (sourceId: widget.sourceId, seriesKey: widget.seriesId);
    final progressMap = ref.watch(sourceProgressProvider);
    final hasScope = ref.watch(activeDownloadsScopeIdProvider) != null;
    final downloadStatuses =
        ref.watch(seriesChapterDownloadStatusProvider(identity)).valueOrNull;
    final wordCounts =
        ref.watch(novelSeriesWordCountsProvider(identity)).valueOrNull ??
            const <String, int>{};

    final ordered = sortSeriesChapters(
      widget.chapters,
      numberOf: (chapter) => chapter.number,
      order: _sortOrder,
    );
    final estimate = estimateSeriesLength(
      widget.chapters.isNotEmpty ? widget.chapters.length : series.chapterCount,
      wordCounts.values,
    );

    return CustomScrollView(
      slivers: [
        SliverToBoxAdapter(
          child: _FrontMatter(
            series: series,
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            chapterCount: widget.chapters.isNotEmpty
                ? widget.chapters.length
                : series.chapterCount,
            estimate: estimate,
            chapters: widget.chapters,
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.lg,
            AppSpacing.xl,
            AppSpacing.lg,
            AppSpacing.sm,
          ),
          sliver: SliverToBoxAdapter(
            child: Row(
              children: [
                Text(
                  'CONTENTS',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 2,
                    fontWeight: FontWeight.w700,
                    color: colors.muted,
                  ),
                ),
                const Spacer(),
                SeriesChapterSortToggle(
                  value: _sortOrder,
                  onChanged: (order) => setState(() => _sortOrder = order),
                ),
              ],
            ),
          ),
        ),
        if (ordered.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl),
              child: Center(
                child: Text(
                  'This source did not return any chapters for this book.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: colors.muted),
                ),
              ),
            ),
          )
        else
          SliverList.builder(
            itemCount: ordered.length,
            itemBuilder: (context, index) {
              final chapter = ordered[index];
              return _TocRow(
                chapter: chapter,
                wordCount: wordCounts[chapter.id],
                progress: progressMap[sourceProgressKey(
                  sourceId: widget.sourceId,
                  seriesId: widget.seriesId,
                  chapterId: chapter.id,
                )],
                hasScope: hasScope,
                status: downloadStatuses?[chapter.id],
                onOpen: () => context.push(
                  RoutePaths.novelReader(
                    widget.sourceId,
                    widget.seriesId,
                    chapter.id,
                  ),
                ),
                identity: (
                  sourceId: widget.sourceId,
                  seriesKey: widget.seriesId,
                  chapterKey: chapter.id,
                ),
                seriesTitle: series.title,
              );
            },
          ),
        SliverToBoxAdapter(
          child: SizedBox(
            height: AppSpacing.xl5 + MediaQuery.paddingOf(context).bottom,
          ),
        ),
      ],
    );
  }
}

class _FrontMatter extends ConsumerWidget {
  const _FrontMatter({
    required this.series,
    required this.sourceId,
    required this.seriesId,
    required this.chapterCount,
    required this.estimate,
    required this.chapters,
  });

  final SourceSeriesSummary series;
  final String sourceId;
  final String seriesId;
  final int chapterCount;
  final SeriesLengthEstimate estimate;
  final List<SourceChapterSummary> chapters;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.colors;
    const serif = kNovelSerifStack;
    final meta = [
      byline(series.author),
      formatChapterCount(chapterCount),
      formatStatus(series.status),
    ].whereType<String>().join('  ·  ');
    final blurb = shelfBlurb(series.description);
    final genres = shelfGenres(series.genres);

    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg,
        0,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      series.title,
                      style: TextStyle(
                        fontFamily: serif.first,
                        fontFamilyFallback: serif.sublist(1),
                        fontSize: 27,
                        height: 1.2,
                        fontWeight: FontWeight.w600,
                        color: colors.fg,
                      ),
                    ),
                    if (meta.isNotEmpty) ...[
                      const SizedBox(height: AppSpacing.sm),
                      Text(
                        meta,
                        style: TextStyle(fontSize: 13, color: colors.muted),
                      ),
                    ],
                  ],
                ),
              ),
              // Small and subordinate — present when the art is real, never
              // the thing the page is built around.
              if (series.coverUrl.isNotEmpty) ...[
                const SizedBox(width: AppSpacing.lg),
                ClipRRect(
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  child: SizedBox(
                    width: 76,
                    height: 112,
                    child: SeriesCoverImage(
                      url: series.coverUrl,
                      borderRadius: 0,
                    ),
                  ),
                ),
              ],
            ],
          ),
          if (_lengthLine() != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text(
              _lengthLine()!,
              style: TextStyle(fontSize: 12, color: colors.muted),
            ),
          ],
          const SizedBox(height: AppSpacing.lg),
          if (chapters.isNotEmpty) ...[
            _ReadButton(
              sourceId: sourceId,
              seriesId: seriesId,
              chapters: chapters,
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          Row(
            children: [
              Expanded(
                child: SeriesFollowButton(
                  key: const Key('follow-toggle'),
                  sourceId: sourceId,
                  seriesKey: seriesId,
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              DownloadSeriesButton(
                // The whole book, fetched in server-sized windows rather than
                // one request per chapter — see
                // `DownloadQueueController._primeNovelWindow`.
                label: 'Download book',
                chapters: [
                  for (final chapter in chapters)
                    (
                      id: (
                        sourceId: sourceId,
                        seriesKey: seriesId,
                        chapterKey: chapter.id,
                      ),
                      chapterNumber: chapter.number,
                      title: chapter.title,
                      seriesTitle: series.title,
                      // Prose, so the queue fetches /novels/chapter and stores
                      // one small text blob instead of a page loop.
                      kind: DownloadKind.novel,
                    ),
                ],
              ),
            ],
          ),
          if (blurb != null) ...[
            const SizedBox(height: AppSpacing.lg),
            Text(
              blurb,
              style: TextStyle(
                fontFamily: serif.first,
                fontFamilyFallback: serif.sublist(1),
                fontSize: 15,
                height: 1.6,
                color: colors.fg,
              ),
            ),
          ],
          if (genres.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                for (final genre in genres)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(AppRadius.sm),
                      border: Border.all(color: colors.border),
                    ),
                    child: Text(
                      genre,
                      style: TextStyle(fontSize: 11, color: colors.muted),
                    ),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// "≈ 1.1M words · ≈ 73 h — estimated from 5 chapters", or nothing.
  ///
  /// Never presented as a count: the qualifier is part of the line, not a
  /// footnote, because the number is a projection from whatever chapters the
  /// phone happens to hold.
  String? _lengthLine() {
    final words = formatEstimatedWords(estimate);
    final time = formatEstimatedTotal(estimate);
    if (words == null || time == null) return null;
    final from = estimate.sampleSize == 1
        ? '1 chapter'
        : '${estimate.sampleSize} chapters';
    return '$words  ·  $time    estimated from $from';
  }
}

/// "Start reading" / "Continue" — the one control a book page needs above
/// everything else.
///
/// The resume rule is the manga screen's, unchanged: a finished chapter
/// advances to the next unread one at the top, an unfinished one reopens at
/// the stored position. The only difference is what the stored position means
/// — a paragraph bucket rather than a page — and since both ride `?page=`,
/// this needs no arithmetic of its own.
class _ReadButton extends ConsumerWidget {
  const _ReadButton({
    required this.sourceId,
    required this.seriesId,
    required this.chapters,
  });

  final String sourceId;
  final String seriesId;
  final List<SourceChapterSummary> chapters;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Watched, not read: finishing a chapter in the reader and coming back
    // must flip this from "Continue" to the next chapter without a refresh.
    ref.watch(sourceProgressProvider);
    final resume = ref.read(sourceProgressProvider.notifier).latestForSeries(
          sourceId: sourceId,
          seriesId: seriesId,
        );
    final ordered = sortSeriesChapters(
      chapters,
      numberOf: (chapter) => chapter.number,
      order: SeriesChapterSortOrder.oldest,
    );

    String target;
    if (resume != null) {
      final index = ordered.indexWhere((c) => c.id == resume.chapterId);
      final next = resume.progress.completed &&
              index != -1 &&
              index + 1 < ordered.length
          ? ordered[index + 1]
          : null;
      if (next != null) {
        target = RoutePaths.novelReader(sourceId, seriesId, next.id);
      } else {
        target = '${RoutePaths.novelReader(sourceId, seriesId, resume.chapterId)}'
            '?page=${resume.progress.page}';
      }
    } else {
      target = RoutePaths.novelReader(sourceId, seriesId, ordered.first.id);
    }

    return PrimaryPillButton(
      key: const Key('read-primary'),
      expanded: true,
      onPressed: () => context.push(target),
      icon: resume != null
          ? Icons.play_arrow_rounded
          : Icons.menu_book_outlined,
      label: resume != null ? 'Continue' : 'Start reading',
    );
  }
}

class _TocRow extends ConsumerWidget {
  const _TocRow({
    required this.chapter,
    required this.wordCount,
    required this.progress,
    required this.hasScope,
    required this.status,
    required this.onOpen,
    required this.identity,
    required this.seriesTitle,
  });

  final SourceChapterSummary chapter;
  final int? wordCount;
  final SourceChapterProgress? progress;
  final bool hasScope;
  final ChapterDownloadStatus? status;
  final VoidCallback onOpen;
  final ({String sourceId, String seriesKey, String chapterKey}) identity;
  final String seriesTitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.colors;
    final entry = tocEntry(number: chapter.number, title: chapter.title);
    final read = progress?.completed ?? false;
    const serif = kNovelSerifStack;

    // Words and minutes when the phone actually has the chapter; otherwise
    // nothing, rather than a guess. A novel chapter's page count is always 0.
    final length = formatChapterLength(wordCount);

    return InkWell(
      onTap: onOpen,
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.lg,
          vertical: AppSpacing.sm + 2,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: 40,
              child: Text(
                entry.ordinal ?? '·',
                style: TextStyle(
                  fontFamily: serif.first,
                  fontFamilyFallback: serif.sublist(1),
                  fontSize: 16,
                  color: read ? colors.muted : colors.fg,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (entry.title != null)
                    Text(
                      entry.title!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontFamily: serif.first,
                        fontFamilyFallback: serif.sublist(1),
                        fontSize: 15,
                        height: 1.35,
                        color: read ? colors.muted : colors.fg,
                      ),
                    ),
                  if (length != null || progress != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        [
                          if (length != null) length,
                          if (read)
                            'Read'
                          else if (progress != null)
                            '${progress!.page}% in',
                        ].join('  ·  '),
                        style: TextStyle(fontSize: 11, color: colors.muted),
                      ),
                    ),
                ],
              ),
            ),
            // The same control the manga rows use, decided by the same
            // mapping — a novel chapter is queued, retried and finished
            // exactly like any other row in the store.
            if (chapterDownloadAction(
                  hasScope: hasScope,
                  status: status,
                  buttonKey: Key('download-${chapter.id}'),
                  onDownload: () => ref
                      .read(downloadQueueControllerProvider.notifier)
                      .enqueueChapter(
                        id: identity,
                        chapterNumber: chapter.number,
                        title: chapter.title,
                        seriesTitle: seriesTitle,
                        kind: DownloadKind.novel,
                      ),
                ) case final action?)
              SeriesChapterDownloadControl(download: action),
          ],
        ),
      ),
    );
  }
}
