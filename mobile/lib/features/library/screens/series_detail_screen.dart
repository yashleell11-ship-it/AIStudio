import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_selection.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/series_download_status_provider.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/chapter_download_action.dart';
import 'package:manhwamaniacs/features/downloads/widgets/chapter_selection_actions.dart';
import 'package:manhwamaniacs/features/downloads/widgets/download_series_button.dart';
import 'package:manhwamaniacs/features/downloads/widgets/series_download_progress.dart';
import 'package:manhwamaniacs/features/library/models/known_chapter.dart';
import 'package:manhwamaniacs/features/library/models/series_detail.dart';
import 'package:manhwamaniacs/features/library/providers/series_detail_provider.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/utils/series_display.dart';
import 'package:manhwamaniacs/features/library/widgets/series_detail/series_detail_skeleton.dart';
import 'package:manhwamaniacs/features/reader/widgets/read_all_button.dart';
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

/// The library (followed) series page.
///
/// Deliberately built from the same shared parts as the source-browse series
/// page (`SourceSeriesDetailScreen`): same app bar, same header, same action
/// order, same chapter rows, same Newest/Oldest sort. Arriving here by tapping
/// a chapter title in the reader used to land on a page that looked and behaved
/// like a different app; everything that differs now is a difference in what is
/// actually known about the series, not in how it is presented.
///
/// Reached only for a series the profile already follows — [seriesId] is the
/// follow row's `followed_id` (`GET /library/series/{followed_id}`), a handle
/// for this page's own mutations, never the series' domain identity (that is
/// `(sourceId, seriesKey)`, both always present here).
class SeriesDetailScreen extends ConsumerWidget {
  const SeriesDetailScreen({super.key, required this.seriesId});

  final int seriesId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final seriesAsync = ref.watch(seriesDetailProvider(seriesId));
    // Name the screen after the series, matching the source page.
    final title = seriesAsync.valueOrNull?.series.title;

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
        data: (view) => _SeriesDetailContent(
          series: view.series,
          isOffline: view.isOffline,
        ),
      ),
    );
  }
}

class _SeriesDetailContent extends ConsumerStatefulWidget {
  const _SeriesDetailContent({required this.series, required this.isOffline});

  final SeriesDetail series;

  /// Rebuilt from the device because the server could not be reached, so
  /// [SeriesDetail.chapters] is what has been downloaded rather than what
  /// exists. The page has to say so.
  final bool isOffline;

  @override
  ConsumerState<_SeriesDetailContent> createState() =>
      _SeriesDetailContentState();
}

class _SeriesDetailContentState extends ConsumerState<_SeriesDetailContent> {
  late SeriesDetail _series;

  SeriesChapterSortOrder _sortOrder = SeriesChapterSortOrder.newest;

  /// The chapter list the two orderings below were built from — the memo key,
  /// compared by identity because [SeriesDetail] hands out the same list until
  /// the payload itself is replaced.
  List<KnownChapter> _sortedFrom = const [];
  List<KnownChapter> _newestFirst = const [];
  List<KnownChapter> _oldestFirst = const [];

  /// Multi-select state for this visit to this page (spec R4). Owned here,
  /// disposed here — leaving the series must forget the selection.
  final _selection = ChapterSelectionController();

  @override
  void initState() {
    super.initState();
    _series = widget.series;
    // The rows carry the checkboxes but the range helpers live in the action
    // bar, so a "Next 10" tap has to repaint the list too.
    _selection.addListener(_onSelectionChanged);
  }

  @override
  void dispose() {
    _selection
      ..removeListener(_onSelectionChanged)
      ..dispose();
    super.dispose();
  }

  void _onSelectionChanged() {
    if (mounted) setState(() {});
  }

  /// Rebuilds both chapter orderings, but only when the chapters changed.
  ///
  /// One build needs newest-first (the header's "Latest:" line), oldest-first
  /// (Continue, and the order the multi-select ranges are defined against) and
  /// whichever of the two the sort toggle is showing. Deriving those in `build`
  /// meant four allocate-index-sort-rebuild passes over the whole chapter list
  /// — on every selection tap, every sort toggle, and every page of every
  /// download, since the live progress provider ticks once per page fetched.
  void _ensureSorted() {
    if (identical(_sortedFrom, _series.chapters)) return;
    _sortedFrom = _series.chapters;
    _newestFirst = sortSeriesChapters(
      _sortedFrom,
      numberOf: (chapter) => chapter.number,
      order: SeriesChapterSortOrder.newest,
    );
    _oldestFirst = sortSeriesChapters(
      _sortedFrom,
      numberOf: (chapter) => chapter.number,
      order: SeriesChapterSortOrder.oldest,
    );
  }

  @override
  void didUpdateWidget(_SeriesDetailContent oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.series.id != oldWidget.series.id ||
        widget.series.updatedAt != oldWidget.series.updatedAt) {
      _series = widget.series;
    }
  }

  Future<void> _toggleFavorite() async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.patchSeries(
      _series.id,
      isFavorite: !_series.isFavorite,
    );
    if (!mounted) return;
    if (result.isErr) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.error.userMessage)),
      );
      return;
    }
    setState(() => _series = _series.copyWith(isFavorite: result.value.isFavorite));
  }

  void _openChapter(KnownChapter chapter, {int? page, bool readAll = false}) {
    // Prose opens the novel reader. `page` carries a progress bucket rather
    // than a page number there, but it is the same parameter and the same
    // 1-based meaning, so only the path differs.
    final isNovel = ref.read(contentModeScopeProvider).modeOf(_series.sourceId) ==
        ContentMode.novel;
    final path = isNovel
        ? RoutePaths.novelReader(
            _series.sourceId,
            _series.seriesKey,
            chapter.key,
          )
        : readAll
            ? RoutePaths.readAll(
                _series.sourceId,
                _series.seriesKey,
                chapter.key,
              )
            : RoutePaths.reader(
                _series.sourceId,
                _series.seriesKey,
                chapter.key,
              );
    if (page == null) {
      context.push(path);
      return;
    }
    // Read-all's path already carries a query, so the page joins it rather
    // than starting a second one.
    context.push('$path${path.contains('?') ? '&' : '?'}page=$page');
  }

  /// Newest chapter for the header meta line — the highest-numbered row in the
  /// list the page is about to render, so the line and the list agree.
  String? _latestChapterLabel() {
    final newest = _newestFirst.firstOrNull;
    if (newest == null) return null;
    return chapterLabel(number: newest.number, title: newest.title).primary;
  }

  /// The chapter "Continue"/"Start Reading" would open: the highest-numbered
  /// chapter with unfinished progress, or the first chapter when nothing has
  /// been read yet.
  KnownChapter? _continueChapter() {
    KnownChapter? inProgress;
    for (final chapter in _oldestFirst) {
      final entry = _series.progress[chapter.key];
      if (entry != null && !entry.isCompleted) inProgress = chapter;
    }
    return inProgress ?? _oldestFirst.firstOrNull;
  }

  /// This series' domain identity — the key every downloads provider is
  /// keyed by, and never the follow row's [SeriesDetail.id].
  SeriesIdentity get _identity =>
      (sourceId: _series.sourceId, seriesKey: _series.seriesKey);

  @override
  Widget build(BuildContext context) {
    _ensureSorted();
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final continueChapter = _continueChapter();
    final continueProgress =
        continueChapter == null ? null : _series.progress[continueChapter.key];

    final sortedChapters = _sortOrder == SeriesChapterSortOrder.newest
        ? _newestFirst
        : _oldestFirst;

    // Watched once for the whole page rather than per row: one store query
    // and one queue subscription drive every chapter's download state.
    final downloadStatuses = ref
        .watch(seriesChapterDownloadStatusProvider(_identity))
        .valueOrNull;
    final activeProgress =
        ref.watch(seriesActiveChapterProgressProvider(_identity));
    final hasScope = ref.watch(activeDownloadsScopeIdProvider) != null;
    // What a download of this series holds — page images or prose. Resolved
    // from the source-mode index rather than guessed, because it decides both
    // which endpoint the queue fetches and which reader the row opens in.
    final kind = ref.watch(contentModeScopeProvider).modeOf(_series.sourceId) ==
            ContentMode.novel
        ? DownloadKind.novel
        : DownloadKind.manga;

    final statusChips = <SeriesDetailChip>[
      if (_series.readingStatus.isNotEmpty)
        SeriesDetailChip(
          label: readingStatusLabel(_series.readingStatus).toUpperCase(),
          color: readingStatusColor(context, _series.readingStatus),
        ),
      for (final genre in _series.genres ?? const <String>[])
        SeriesDetailChip(label: genre),
    ];

    return SeriesDetailBody(
      cover: Hero(
        tag: seriesCoverHeroTag(_series.id),
        child: SeriesCoverImage(
          url: followedSeriesCoverUrl(baseUrl, _series) ?? '',
          displayWidth: SeriesDetailBody.coverWidthFor(context),
          borderRadius: 0,
        ),
      ),
      title: _series.title,
      author: _series.author,
      metaLine: seriesDetailMetaLine(
        latestChapterLabel: _latestChapterLabel(),
        // The rendered list is authoritative; the payload count is a fallback
        // for a series whose chapters were not expanded.
        chapterCount: _series.chapters.isNotEmpty
            ? _series.chapters.length
            : _series.chapterCount,
      ),
      description: _series.description,
      primaryAction: continueChapter == null
          ? null
          : Row(
              children: [
                Expanded(
                  child: PrimaryPillButton(
                    key: const Key('read-primary'),
                    expanded: true,
                    icon: continueProgress != null
                        ? Icons.play_arrow_rounded
                        : Icons.menu_book_outlined,
                    label:
                        continueProgress != null ? 'Continue' : 'Start Reading',
                    onPressed: () => _openChapter(
                      continueChapter,
                      page: continueProgress?.lastPage,
                    ),
                  ),
                ),
                SizedBox(width: context.space.sm),
                // Prose has no Read-all: a novel is already one continuous
                // scroll per chapter, and the mode exists to remove a page
                // boundary that only manga has.
                if (kind != DownloadKind.novel)
                  ReadAllButton(
                    onPressed: () => _openChapter(
                      continueChapter,
                      page: continueProgress?.lastPage,
                      readAll: true,
                    ),
                  ),
              ],
            ),
      followAction: SeriesFollowButton(
        key: const Key('follow-toggle'),
        sourceId: _series.sourceId,
        seriesKey: _series.seriesKey,
        initialIsFollowed: true,
        initialFollowedId: _series.id,
      ),
      secondaryActions: [
        ChapterSelectionActions(
          controller: _selection,
          identity: _identity,
          chaptersInReadingOrder: _selectableChapters(downloadStatuses),
          seriesTitle: _series.title,
          kind: kind,
        ),
        DownloadSeriesButton(
          chapters: [
            for (final chapter in _series.chapters)
              (
                id: (
                  sourceId: _series.sourceId,
                  seriesKey: _series.seriesKey,
                  chapterKey: chapter.key,
                ),
                chapterNumber: chapter.number,
                title: chapter.title,
                seriesTitle: _series.title,
                kind: kind,
              ),
          ],
        ),
        OutlinedButton.icon(
          key: const Key('favorite-toggle'),
          onPressed: _toggleFavorite,
          icon: Icon(
            _series.isFavorite ? Icons.star : Icons.star_border,
            color: _series.isFavorite ? context.colors.warning : null,
          ),
          label: Text(_series.isFavorite ? 'Favorited' : 'Add Favorite'),
          style: OutlinedButton.styleFrom(
            foregroundColor:
                _series.isFavorite ? context.colors.warning : context.colors.fg,
            side: BorderSide(
              color: _series.isFavorite
                  ? context.colors.warning.withAlpha(77)
                  : context.colors.border,
            ),
            backgroundColor: _series.isFavorite
                ? context.colors.warning.withAlpha(26)
                : context.colors.fg.withAlpha(13),
          ),
        ),
      ],
      details: [
        if (statusChips.isNotEmpty) SeriesDetailChipRow(chips: statusChips),
        if (hasScope)
          SeriesDownloadProgress(
            identity: _identity,
            totalChapters: _series.chapters.length,
          ),
      ],
      sortOrder: _sortOrder,
      onSortOrderChanged: (order) => setState(() => _sortOrder = order),
      emptyChapters: const EmptyState(
        icon: Icons.menu_book_outlined,
        message: 'No chapters available',
        subtitle: "This source hasn't listed any chapters for this series yet.",
      ),
      chapterTiles: [
        for (final chapter in sortedChapters)
          _buildChapterTile(
            chapter,
            hasScope: hasScope,
            status: downloadStatuses?[chapter.key],
            progress: activeProgress?.chapterKey == chapter.key
                ? activeProgress?.progress
                : null,
          ),
      ],
    );
  }

  /// The chapter list as the multi-select ranges see it, oldest first — the
  /// order "next 10" is defined against, independent of the Newest/Oldest
  /// toggle driving what is on screen.
  List<SelectableChapter> _selectableChapters(
    Map<String, ChapterDownloadStatus>? downloadStatuses,
  ) {
    return [
      for (final chapter in _oldestFirst)
        (
          key: chapter.key,
          number: chapter.number,
          title: chapter.title,
          isRead: _series.progress[chapter.key]?.isCompleted ?? false,
          isDownloaded: downloadStatuses?[chapter.key]?.state ==
              DownloadChapterState.complete,
        ),
    ];
  }

  Widget _buildChapterTile(
    KnownChapter chapter, {
    required bool hasScope,
    required ChapterDownloadStatus? status,
    required ChapterDownloadProgress? progress,
  }) {
    final entry = _series.progress[chapter.key];
    final isRead = entry?.isCompleted ?? false;
    final isCurrent = entry != null && !isRead;

    return SeriesChapterTile(
      key: Key('chapter-${chapter.key}'),
      label: chapterLabel(number: chapter.number, title: chapter.title),
      progressText: seriesChapterProgressText(
        pageCount: chapter.pageCount ?? 0,
        page: entry?.lastPage,
        completed: isRead,
      ),
      inProgress: isCurrent,
      isRead: isRead,
      // "Reading" marks the chapter Continue would resume -- the last one
      // opened, and only while it is unfinished.
      isCurrent: isCurrent,
      // While selecting, a row tap ticks the box instead of opening the
      // chapter: nothing else would explain what the checkbox is for.
      onTap: _selection.isActive
          ? () => _selection.toggle(chapter.key)
          : () => _openChapter(chapter),
      selection: _selection.isActive
          ? SeriesChapterSelection(
              selected: _selection.isSelected(chapter.key),
              checkboxKey: Key('select-${chapter.key}'),
              onChanged: (_) => _selection.toggle(chapter.key),
            )
          : null,
      download: chapterDownloadAction(
        hasScope: hasScope,
        status: status,
        progress: progress,
        buttonKey: Key('download-${chapter.key}'),
        onDownload: () => ref.read(downloadQueueControllerProvider.notifier).enqueueChapter(
              id: (
                sourceId: _series.sourceId,
                seriesKey: _series.seriesKey,
                chapterKey: chapter.key,
              ),
              chapterNumber: chapter.number,
              title: chapter.title,
              seriesTitle: _series.title,
            ),
      ),
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
        padding: EdgeInsets.all(context.space.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, color: context.colors.danger, size: 48),
            SizedBox(height: context.space.lg),
            Text('Could not load series', style: context.text.h3),
            SizedBox(height: context.space.sm),
            Text(
              error.userMessage,
              style: context.text.body.copyWith(color: context.colors.muted),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: context.space.xl2),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
            ),
            SizedBox(height: context.space.md),
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
