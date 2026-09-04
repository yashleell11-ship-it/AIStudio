import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/providers/progress_outbox_provider.dart';
import 'package:manhwamaniacs/features/downloads/widgets/open_chapter_scope.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_feed_controller.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_series_navigation.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// The manifest-driven reader for a followed series' chapter — the one
/// reader every non-source-browsing entry point (series detail, continue
/// reading, bookmarks, history) links to. Identity is the opaque
/// `(sourceId, seriesKey, chapterKey)` triple; see [Routes.reader].
///
/// Renders offline when the chapter is downloaded — see
/// [resolvedReaderChapterProvider] for how the manifest fetch and the
/// on-device store fallback are reconciled.
class ReaderScreen extends ConsumerWidget {
  const ReaderScreen({
    super.key,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.initialPage = 1,
    this.readAllOrder,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final int initialPage;

  /// Every chapter of the series in reading order — "Read all" (spec R2).
  /// Null for an ordinary read, which continues one chapter at a time by
  /// asking the server what comes next.
  final List<String>? readAllOrder;

  ChapterManifestKey get _key =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final resolvedAsync = ref.watch(resolvedReaderChapterProvider(_key));
    // Watched, never awaited (spec R3). A chapter rendered from disk knows its
    // own pages but not its neighbours; this fills them in whenever the
    // network can supply them, and stays null forever if it cannot — which
    // costs the reader nothing but the prev/next affordances.
    final neighbours = ref.watch(chapterNeighboursProvider(_key)).valueOrNull;

    void retry() {
      // Both, not just the resolved provider: the manifest is a separate
      // cache entry and a retry that re-read its stored error would be a
      // button that does nothing.
      ref.invalidate(chapterManifestProvider(_key));
      ref.invalidate(resolvedReaderChapterProvider(_key));
    }

    return resolvedAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: retry,
          onBack: () => context.pop(),
        );
      },
      data: (resolved) {
        if (resolved.chapter.pages.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(message: 'This chapter has no pages.'),
            onRetry: retry,
            onBack: () => context.pop(),
          );
        }

        return OpenChapterScope(
          chapterId: _key,
          child: _ManifestReaderBody(
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapterKey,
            resolved: resolved,
            neighbours: neighbours,
            initialPage: initialPage,
            readAllOrder: readAllOrder,
          ),
        );
      },
    );
  }
}

class _ManifestReaderBody extends ConsumerStatefulWidget {
  const _ManifestReaderBody({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.resolved,
    required this.neighbours,
    required this.initialPage,
    this.readAllOrder,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final ResolvedReaderChapter resolved;

  /// Adjacent keys from the manifest, or null while (or if) it never lands.
  /// Only ever *adds* to what [resolved] already carries — a chapter resolved
  /// online got them in the same payload.
  final ChapterNeighbours? neighbours;
  final int initialPage;

  /// Every chapter of the series in reading order — Read-all (spec R2). With
  /// it the feed knows where it is going without a round trip per boundary;
  /// without it the reader is an ordinary one-chapter read that happens to
  /// continue when it reaches the end.
  final List<String>? readAllOrder;

  @override
  ConsumerState<_ManifestReaderBody> createState() => _ManifestReaderBodyState();
}

class _ManifestReaderBodyState extends ConsumerState<_ManifestReaderBody> {
  late ReaderFeedController _controller;

  @override
  void initState() {
    super.initState();
    _controller = _buildController();
  }

  @override
  void didUpdateWidget(covariant _ManifestReaderBody oldWidget) {
    super.didUpdateWidget(oldWidget);
    // The neighbours the screen watches land after first paint (spec R3), and
    // the feed needs them to know what to continue into. Anything else about
    // the anchor changing means a different chapter entirely.
    if (oldWidget.chapterKey != widget.chapterKey ||
        !identical(oldWidget.resolved.chapter, widget.resolved.chapter)) {
      _controller.dispose();
      _controller = _buildController();
      return;
    }
    _controller.noteNeighbours(
      widget.chapterKey,
      prev: _prev,
      next: _next,
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  ReaderFeedController _buildController() => ReaderFeedController(
        anchor: widget.resolved.chapter,
        prev: _prev,
        next: _next,
        order: widget.readAllOrder,
        neighboursOf: _neighboursOf,
        loadChapter: _loadChapter,
      )..addListener(_onFeedChanged);

  void _onFeedChanged() {
    if (mounted) setState(() {});
  }

  String? get _prev => widget.resolved.prev ?? widget.neighbours?.prev;
  String? get _next => widget.resolved.next ?? widget.neighbours?.next;

  /// The number progress is filed under. The store stamps it at download time
  /// from the same manifest, so the two agree; the manifest wins only when the
  /// store had none to stamp.
  double? _chapterNumberOf(ReaderChapter chapter) {
    if (chapter.id == widget.chapterKey) {
      return widget.resolved.chapterNumber ?? widget.neighbours?.chapterNumber;
    }
    return _numbers[chapter.id];
  }

  /// Chapter numbers learned while extending the feed. Progress needs the
  /// number, not just the key — it is the axis that survives a source change.
  final Map<String, double?> _numbers = {};

  ChapterManifestKey _keyFor(String chapterKey) => (
        sourceId: widget.sourceId,
        seriesKey: widget.seriesKey,
        chapterKey: chapterKey,
      );

  /// Reads a provider to completion while keeping it alive for the duration.
  /// A bare `ref.read(p.future)` on an autoDispose family can have the
  /// provider torn down out from under the pending fetch.
  Future<T> _readAlive<T>(AutoDisposeFutureProvider<T> provider) async {
    final subscription = ref.listenManual(provider, (_, __) {});
    try {
      return await ref.read(provider.future);
    } finally {
      subscription.close();
    }
  }

  /// Loads a chapter for the feed through the SAME disk-first provider the
  /// anchor came through, so a downloaded chapter continues into another
  /// downloaded chapter with no network involved at all.
  Future<ReaderChapter?> _loadChapter(String chapterKey) async {
    try {
      final resolved = await _readAlive(
        resolvedReaderChapterProvider(_keyFor(chapterKey)),
      );
      _numbers[chapterKey] = resolved.chapterNumber;
      return resolved.chapter;
    } catch (_) {
      // A seam that cannot be crossed leaves the edge prompt as the way over.
      return null;
    }
  }

  Future<({String? prev, String? next})> _neighboursOf(String chapterKey) async {
    final neighbours =
        await _readAlive(chapterNeighboursProvider(_keyFor(chapterKey)));
    _numbers[chapterKey] ??= neighbours.chapterNumber;
    return (prev: neighbours.prev, next: neighbours.next);
  }

  @override
  Widget build(BuildContext context) {
    final repo = ref.read(readerRepositoryProvider);
    // Resolved once here rather than via `ref.read(...)` inside the
    // callbacks below: `ReaderContent.dispose()` flushes a pending progress
    // save, and by then this widget's own element may already be
    // deactivated — reading a provider through it at that point throws
    // ("Looking up a deactivated widget's ancestor is unsafe"). Plain
    // objects captured here stay safe to call from anywhere.
    final progressOutbox = ref.read(progressOutboxControllerProvider);
    final downloadsStore = ref.read(downloadsStoreProvider);
    final sourceId = widget.sourceId;
    final seriesKey = widget.seriesKey;

    return ReaderContent(
      key: ValueKey('$sourceId:$seriesKey:${widget.chapterKey}'),
      feed: _controller.feed,
      scrollStorageKey: '$sourceId:$seriesKey:${widget.chapterKey}',
      initialPage: widget.initialPage,
      onBack: () => context.pop(),
      onOpenSeries: () => openSeriesFromReader(
        context,
        sourceId: sourceId,
        seriesKey: seriesKey,
      ),
      // The edge prompts are for a boundary the FEED could not absorb — the
      // ends of the series, or a chapter that would not load. Crossing a
      // loaded boundary is scrolling, and never navigation.
      onPreviousChapter: _prev != null
          ? () => context.go(RoutePaths.reader(sourceId, seriesKey, _prev!))
          : null,
      onNextChapter: _next != null
          ? () => context.go(RoutePaths.reader(sourceId, seriesKey, _next!))
          : null,
      onReachedFeedEnd: _controller.extendForward,
      onReachedFeedStart: _controller.extendBackward,
      onSaveProgress: (chapter, page) async {
        final isCompleted = page >= chapter.pageCount;
        // Local-first (spec §3): every save writes to the on-device outbox
        // and is flushed best-effort — the reader never blocks on, or loses
        // a save to, a flaky or absent connection.
        //
        // Filed against the chapter the PAGE belongs to, which in a continuous
        // feed is not always the one the reader opened: reading into chapter
        // 12 records chapter 12, so resume lands there.
        await progressOutbox.save(
          ProgressPush(
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapter.id,
            chapterNumber: _chapterNumberOf(chapter),
            lastPage: page,
            pageCount: chapter.pageCount,
            isCompleted: isCompleted,
          ),
        );
        if (isCompleted) {
          // Read-then-expire (spec §3/§3b): starts the 48h phone-copy timer.
          // A no-op if this chapter was never downloaded.
          await downloadsStore?.markRead(
            (
              sourceId: sourceId,
              seriesKey: seriesKey,
              chapterKey: chapter.id,
            ),
          );
        }
      },
      onAddBookmark: (chapter, page) => repo
          .addBookmark(
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapter.id,
            page: page,
          )
          .then((result) => result.isOk),
    );
  }
}
