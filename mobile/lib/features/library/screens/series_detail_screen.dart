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
import 'package:manhwamaniacs/features/downloads/utils/source_chapter_download_status.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/providers/series_detail_provider.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/features/library/widgets/series_detail/series_detail_skeleton.dart';
import 'package:manhwamaniacs/features/sources/providers/source_series_download_status_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/features/updates/widgets/series_follow_button.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_sort.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_chapter_tile.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_body.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_chips.dart';
import 'package:manhwamaniacs/shared/widgets/series_detail/series_detail_meta.dart';

/// The library (downloaded) series page.
///
/// Deliberately built from the same shared parts as the source-browse series
/// page (`SourceSeriesDetailScreen`): same app bar, same header, same action
/// order, same chapter rows, same Newest/Oldest sort. Arriving here by tapping
/// a chapter title in the reader used to land on a page that looked and behaved
/// like a different app; everything that differs now is a difference in what is
/// actually known about the series, not in how it is presented.
class SeriesDetailScreen extends ConsumerWidget {
  const SeriesDetailScreen({super.key, required this.seriesId});

  final int seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final seriesAsync = ref.watch(seriesDetailProvider(seriesId));
    // Name the screen after the series, matching the source page.
    final title = seriesAsync.valueOrNull?.title;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(Routes.libraryBrowse),
        ),
        title: Text(
          title == null || title.isEmpty ? 'Series' : title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: seriesAsync.when(
        loading: () => const SeriesDetailSkeleton(),
        error: (error, _) => _SeriesDetailError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.invalidate(seriesDetailProvider(seriesId)),
        ),
        data: (series) => _SeriesDetailContent(series: series),
      ),
    );
  }
}

class _SeriesDetailContent extends ConsumerStatefulWidget {
  const _SeriesDetailContent({required this.series});

  final SeriesDetail series;

  @override
  ConsumerState<_SeriesDetailContent> createState() =>
      _SeriesDetailContentState();
}

class _SeriesDetailContentState extends ConsumerState<_SeriesDetailContent> {
  late SeriesDetail _series;

  /// Source chapter ids ticked for a bulk download.
  final Set<String> _selectedChapterIds = {};

  /// A queue request is in flight; guards double taps on every download control.
  bool _downloadPending = false;

  SeriesChapterSortOrder _sortOrder = SeriesChapterSortOrder.newest;

  /// Captured in [didChangeDependencies] so [dispose] can hide the snackbar
  /// without an (unsafe) inherited-widget lookup on a deactivated element.
  ScaffoldMessengerState? _messenger;

  @override
  void initState() {
    super.initState();
    _series = widget.series;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _messenger = ScaffoldMessenger.maybeOf(context);
  }

  @override
  void didUpdateWidget(_SeriesDetailContent oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.series.id != oldWidget.series.id ||
        widget.series.updatedAt != oldWidget.series.updatedAt) {
      _series = widget.series;
    }
  }

  @override
  void dispose() {
    _messenger?.hideCurrentSnackBar();
    super.dispose();
  }

  Future<void> _toggleFavorite() async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.toggleFavorite(_series.id);
    if (!mounted) return;
    if (result.isErr) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.error.userMessage)),
      );
      return;
    }
    setState(() {
      _series = _series.copyWith(isFavorite: !_series.isFavorite);
    });
  }

  /// Open a remote-only chapter in the source reader.
  void _readOnline(ChapterSummary chapter) {
    final sourceChapterId = chapter.sourceChapterId;
    if (!_series.hasSourceLink || sourceChapterId == null) return;
    context.push(
      RoutePaths.sourceReader(
        _series.sourceId!,
        _series.sourceSeriesId!,
        sourceChapterId,
      ),
    );
  }

  void _toggleChapter(String sourceChapterId) {
    setState(() {
      if (_selectedChapterIds.contains(sourceChapterId)) {
        _selectedChapterIds.remove(sourceChapterId);
      } else {
        _selectedChapterIds.add(sourceChapterId);
      }
    });
  }

  void _showQueueFeedback(QueueDownloadResponse response) {
    if (!mounted) return;
    showQueueDownloadSnackBar(context, response);
  }

  Future<void> _queueChapters(List<String> chapterIds) async {
    if (!_series.hasSourceLink || chapterIds.isEmpty || _downloadPending) return;

    setState(() => _downloadPending = true);
    try {
      final result = await ref.read(downloadsProvider.notifier).queueChapters(
            sourceId: _series.sourceId!,
            seriesId: _series.sourceSeriesId!,
            chapterIds: chapterIds,
            seriesTitle: _series.title,
          );
      if (!mounted) return;
      if (result.isErr) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(result.error.userMessage)),
        );
        return;
      }
      setState(() => _selectedChapterIds.removeAll(chapterIds));
      _showQueueFeedback(result.value);
    } finally {
      if (mounted) {
        setState(() => _downloadPending = false);
      }
    }
  }

  Future<void> _downloadSeries() async {
    if (!_series.hasSourceLink || _downloadPending) return;

    setState(() => _downloadPending = true);
    try {
      final result = await ref.read(downloadsProvider.notifier).queueSeries(
            sourceId: _series.sourceId!,
            seriesId: _series.sourceSeriesId!,
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

  /// Newest chapter for the header meta line — the highest-numbered row in the
  /// list the page is about to render, so the line and the list agree.
  String? _latestChapterLabel() {
    final newest = sortSeriesChapters(
      _series.chapters,
      numberOf: (chapter) => chapter.number,
      order: SeriesChapterSortOrder.newest,
    ).firstOrNull;
    if (newest == null) return null;
    return chapterLabel(number: newest.number, title: newest.title).primary;
  }

  @override
  Widget build(BuildContext context) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final progress = _series.readingProgress;
    final continueChapterId = progress?.chapterId ?? _series.firstChapterId;
    final continuePage = progress?.lastPage;
    final hasSourceLink = _series.hasSourceLink;

    // Live download state for the chapters that are not on disk yet. Only
    // meaningful for a series that resolves back to a source, and the family
    // key needs both ids non-null, so it is watched only in that case.
    final downloadLookup = hasSourceLink
        ? ref.watch(
            sourceSeriesChapterDownloadLookupProvider(
              (
                sourceId: _series.sourceId!,
                seriesId: _series.sourceSeriesId!,
              ),
            ),
          )
        : const SourceChapterDownloadLookup.empty();

    final sortedChapters = sortSeriesChapters(
      _series.chapters,
      numberOf: (chapter) => chapter.number,
      order: _sortOrder,
    );

    final language = languageLabel(_series.language);
    final statusChips = <SeriesDetailChip>[
      if (_series.readingStatus.isNotEmpty)
        SeriesDetailChip(
          label: readingStatusLabel(_series.readingStatus).toUpperCase(),
          color: readingStatusColor(_series.readingStatus),
        ),
      // An empty language would render an empty pill -- a box with nothing in
      // it says less than no box.
      if (language.isNotEmpty) SeriesDetailChip(label: language),
      if (_series.year != null) SeriesDetailChip(label: '${_series.year}'),
    ];

    return SeriesDetailBody(
      cover: Hero(
        tag: seriesCoverHeroTag(_series.id),
        child: SeriesCoverImage(
          url: seriesCoverUrl(baseUrl, _series.id),
          borderRadius: 0,
        ),
      ),
      title: _series.title,
      originalTitle: _series.originalTitle,
      author: _series.author,
      artist: _series.artist,
      metaLine: seriesDetailMetaLine(
        latestChapterLabel: _latestChapterLabel(),
        // The rendered list is authoritative; the payload count is a fallback
        // for a series whose chapters were not expanded.
        chapterCount: _series.chapters.isNotEmpty
            ? _series.chapters.length
            : _series.chapterCount,
        // Page count and read percentage are library-only facts -- the source
        // catalog cannot know either -- but they belong on the same line as
        // everything else rather than in a separate row of their own.
        pageCount: _series.pageCount,
        readPct: progress?.progressPct,
      ),
      description: _series.description,
      primaryAction: continueChapterId == null
          ? null
          : PrimaryPillButton(
              key: const Key('read-primary'),
              expanded: true,
              icon: progress != null
                  ? Icons.play_arrow_rounded
                  : Icons.menu_book_outlined,
              label: progress != null ? 'Continue' : 'Start Reading',
              onPressed: () {
                final path =
                    '${RoutePaths.seriesDetail(_series.id)}/chapters/$continueChapterId/read';
                context.push(
                  continuePage != null ? '$path?page=$continuePage' : path,
                );
              },
            ),
      // Shown only when the series resolves back to a source: a hand-imported
      // CBZ folder has no origin to check for updates, and a button that is
      // always there but sometimes fails is worse than one that is absent when
      // it cannot work.
      followAction: hasSourceLink
          ? SeriesFollowButton(
              key: const Key('follow-toggle'),
              sourceId: _series.sourceId!,
              seriesId: _series.sourceSeriesId!,
              seriesTitle: _series.title,
              initialIsFollowed: _series.isFollowed,
              initialFollowTrackerId: _series.followTrackerId,
            )
          : null,
      secondaryActions: [
        // Downloads lead, in the same order as the source page, so the two
        // action rows line up; Favourite is the library-only extra and follows.
        if (hasSourceLink) ...[
          OutlinedButton.icon(
            key: const Key('download-series'),
            onPressed: _downloadPending ? null : _downloadSeries,
            icon: const Icon(Icons.download_outlined),
            label: const Text('Download Series'),
          ),
          OutlinedButton.icon(
            key: const Key('download-selected'),
            onPressed: _downloadPending || _selectedChapterIds.isEmpty
                ? null
                : () => _queueChapters(_selectedChapterIds.toList()),
            icon: const Icon(Icons.playlist_add_check_outlined),
            label: const Text('Download Selected'),
          ),
        ],
        OutlinedButton.icon(
          key: const Key('favorite-toggle'),
          onPressed: _toggleFavorite,
          icon: Icon(
            _series.isFavorite ? Icons.star : Icons.star_border,
            color: _series.isFavorite ? AppColors.warning : null,
          ),
          label: Text(_series.isFavorite ? 'Favorited' : 'Add Favorite'),
          style: OutlinedButton.styleFrom(
            foregroundColor:
                _series.isFavorite ? AppColors.warning : AppColors.fg,
            side: BorderSide(
              color: _series.isFavorite
                  ? AppColors.warning.withAlpha(77)
                  : AppColors.border,
            ),
            backgroundColor: _series.isFavorite
                ? AppColors.warning.withAlpha(26)
                : AppColors.fg.withAlpha(13),
          ),
        ),
      ],
      details: [
        // Reading status / language / year keep the pill treatment they had,
        // now in the same slot the source page uses for status and genres.
        if (statusChips.isNotEmpty) SeriesDetailChipRow(chips: statusChips),
        if (_series.tags.isNotEmpty)
          SeriesDetailChipRow(
            chips: [
              for (final tag in _series.tags)
                SeriesDetailChip(label: tag.name, color: tag.color),
            ],
          ),
        if (_series.collections.isNotEmpty)
          Text.rich(
            TextSpan(
              style: AppTypography.body.copyWith(color: AppColors.muted),
              children: [
                const TextSpan(text: 'In collections: '),
                for (var i = 0; i < _series.collections.length; i++) ...[
                  if (i > 0) const TextSpan(text: ', '),
                  TextSpan(
                    text: _series.collections[i].name,
                    style: const TextStyle(color: AppColors.primary),
                  ),
                ],
              ],
            ),
          ),
      ],
      sortOrder: _sortOrder,
      onSortOrderChanged: (order) => setState(() => _sortOrder = order),
      emptyChapters: const EmptyState(
        icon: Icons.menu_book_outlined,
        message: 'No chapters available',
        subtitle: 'Nothing has been downloaded for this series yet.',
      ),
      chapterTiles: [
        for (final chapter in sortedChapters)
          _buildChapterTile(chapter, downloadLookup),
      ],
    );
  }

  Widget _buildChapterTile(
    ChapterSummary chapter,
    SourceChapterDownloadLookup downloadLookup,
  ) {
    final progress = _series.readingProgress;
    final sourceChapterId = chapter.sourceChapterId;
    final canReadLocal = chapter.isDownloaded && chapter.id != null;
    final canReadOnline = _series.hasSourceLink && sourceChapterId != null;
    final isLastRead =
        progress != null && chapter.id != null && progress.chapterId == chapter.id;

    VoidCallback? onTap;
    if (canReadLocal) {
      onTap = () => context.push(
            '${RoutePaths.seriesDetail(_series.id)}/chapters/${chapter.id}/read',
          );
    } else if (canReadOnline) {
      onTap = () => _readOnline(chapter);
    }

    // A chapter already on disk is a finished download; anything else takes its
    // state from the live queue. Both render through the same badge, so a
    // downloaded chapter and a just-downloaded one do not look like different
    // kinds of thing.
    final downloadStatus = chapter.isDownloaded
        ? SourceChapterDownloadUiStatus.completed
        : (sourceChapterId == null
            ? SourceChapterDownloadUiStatus.none
            : downloadLookup.statusFor(sourceChapterId));

    final selectable = canReadOnline && !chapter.isDownloaded;

    return SeriesChapterTile(
      key: Key('chapter-${chapter.id ?? sourceChapterId ?? chapter.title}'),
      label: chapterLabel(number: chapter.number, title: chapter.title),
      progressText: seriesChapterProgressText(
        pageCount: chapter.pageCount,
        page: isLastRead ? progress.lastPage : null,
        completed: chapter.isRead,
      ),
      inProgress: isLastRead && !chapter.isRead,
      downloadStatus: downloadStatus,
      statusBadgeKey: sourceChapterId == null
          ? null
          : Key('chapter-status-$sourceChapterId'),
      isRead: chapter.isRead,
      // "Reading" marks the chapter Continue would resume -- the last one
      // opened, and only while it is unfinished.
      isCurrent: isLastRead && !chapter.isRead,
      onTap: onTap,
      // The checkbox stays present (disabled) on already-downloaded rows so the
      // list keeps one alignment instead of two.
      selection: _series.hasSourceLink
          ? SeriesChapterSelection(
              checkboxKey: sourceChapterId == null
                  ? null
                  : Key('select-$sourceChapterId'),
              selected: sourceChapterId != null &&
                  _selectedChapterIds.contains(sourceChapterId),
              onChanged: !selectable || _downloadPending
                  ? null
                  : (_) => _toggleChapter(sourceChapterId),
            )
          : null,
      download: canReadOnline
          ? SeriesChapterDownloadAction(
              buttonKey: Key('download-$sourceChapterId'),
              retryable: downloadLookup.isRetryable(sourceChapterId),
              onPressed: chapter.isDownloaded ||
                      _downloadPending ||
                      downloadLookup.isDownloadDisabled(sourceChapterId)
                  ? null
                  : () => _queueChapters([sourceChapterId]),
            )
          : null,
    );
  }
}

class _SeriesDetailError extends StatelessWidget {
  const _SeriesDetailError({
    required this.error,
    required this.onRetry,
  });

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 48),
            const SizedBox(height: AppSpacing.lg),
            Text('Could not load series', style: AppTypography.h3),
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl2),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
            ),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              onPressed: () => context.canPop()
                  ? context.pop()
                  : context.go(Routes.libraryBrowse),
              child: const Text('Back to library'),
            ),
          ],
        ),
      ),
    );
  }
}
