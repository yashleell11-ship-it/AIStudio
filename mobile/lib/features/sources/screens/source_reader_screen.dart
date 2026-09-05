import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/network_connectivity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/queue/download_queue_controller.dart';
import 'package:manhwamaniacs/features/downloads/widgets/open_chapter_scope.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/providers/series_reading_order_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_feed_controller.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_series_navigation.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';

/// Online source chapter reader.
///
/// Reuses [ReaderContent] for the full reading experience (fullscreen, zoom,
/// virtualization, image cache, auto-next). Online chapters have no local
/// series, so progress is persisted client-side via [sourceProgressProvider]
/// (the shared cross-platform contract) rather than the library progress API.
///
/// Eagerly queues the next chapter for download the moment this one loads —
/// gated on the "Wi-Fi only downloads" setting so idly reading never burns
/// mobile data the user didn't ask to spend — via the same on-device queue
/// a manual "Download" tap uses (spec §3).
class SourceReaderScreen extends ConsumerStatefulWidget {
  const SourceReaderScreen({
    super.key,
    required this.sourceId,
    required this.seriesId,
    required this.chapterId,
    this.initialPage = 1,
    this.readAll = false,
  });

  final String sourceId;
  final String seriesId;
  final String chapterId;
  final int initialPage;

  /// Read the whole series as one continuous scroll (spec R2) rather than this
  /// chapter and whatever it continues into. The chapter order arrives behind
  /// the first chapter, so the reader still opens in normal time.
  final bool readAll;

  @override
  ConsumerState<SourceReaderScreen> createState() => _SourceReaderScreenState();
}

class _SourceReaderScreenState extends ConsumerState<SourceReaderScreen> {
  /// Guards the eager next-chapter queue so it fires once per chapter shown,
  /// not on every unrelated rebuild of this widget.
  String? _prefetchedFor;

  /// The continuous feed (spec R1). Built the moment the anchor chapter
  /// resolves; null until then.
  ReaderFeedController? _feedController;

  @override
  void dispose() {
    _feedController?.dispose();
    super.dispose();
  }

  SourceReaderChapterKey _keyFor(String chapterId) => (
        sourceId: widget.sourceId,
        seriesId: widget.seriesId,
        chapterId: chapterId,
      );

  /// Reads a provider to completion while keeping it alive for the duration —
  /// a bare `ref.read(p.future)` on an autoDispose family can be torn down out
  /// from under the pending fetch.
  Future<T> _readAlive<T>(AutoDisposeFutureProvider<T> provider) async {
    final subscription = ref.listenManual(provider, (_, __) {});
    try {
      return await ref.read(provider.future);
    } finally {
      subscription.close();
    }
  }

  /// Loads a chapter for the feed through the same disk-first provider the
  /// anchor came through, so a downloaded chapter continues into another
  /// downloaded chapter with no network at all.
  Future<ReaderChapter?> _loadChapter(String chapterId) async {
    try {
      return await _readAlive(sourceReaderChapterProvider(_keyFor(chapterId)));
    } catch (_) {
      // A seam that cannot be crossed leaves the edge prompt as the way over.
      return null;
    }
  }

  Future<({String? prev, String? next})> _neighboursOf(String chapterId) async {
    final neighbours =
        await _readAlive(sourceChapterNeighboursProvider(_keyFor(chapterId)));
    return (
      prev: neighbours.previousChapterId,
      next: neighbours.nextChapterId,
    );
  }

  /// Builds the feed once the anchor is in hand, and keeps its idea of the
  /// anchor's neighbours current as they arrive out of band (spec R3).
  ReaderFeedController _feedFor(
    ReaderChapter chapter, {
    required String? previousChapterId,
    required String? nextChapterId,
  }) {
    final existing = _feedController;
    if (existing != null && existing.feed.contains(chapter.id)) {
      existing.noteNeighbours(
        chapter.id,
        prev: previousChapterId,
        next: nextChapterId,
      );
      return existing;
    }
    existing?.dispose();
    final controller = ReaderFeedController(
      anchor: chapter,
      prev: previousChapterId,
      next: nextChapterId,
      neighboursOf: _neighboursOf,
      loadChapter: _loadChapter,
    )..addListener(() {
        if (mounted) setState(() {});
      });
    _feedController = controller;
    return controller;
  }

  Future<void> _saveProgress(ReaderChapter chapter, int page) async {
    // ReaderContent flushes progress from its dispose(), by which point this
    // state (and its ref/context) may already be deactivated — swallow that
    // race so a normal reader teardown never throws.
    //
    // Filed against the chapter the PAGE belongs to: a continuous feed spans
    // several, and recording all of them against the one the reader opened
    // would put resume in the wrong place.
    final pageCount = chapter.pageCount;
    try {
      await ref.read(sourceProgressProvider.notifier).record(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            chapterId: chapter.id,
            page: page,
            pageCount: pageCount,
          );
      if (pageCount > 0 && page >= pageCount) {
        // Read-then-expire (spec §3/§3b): starts the 48h phone-copy timer.
        // A no-op if this chapter was never downloaded.
        await ref.read(downloadsStoreProvider)?.markRead(
              (
                sourceId: widget.sourceId,
                seriesKey: widget.seriesId,
                chapterKey: chapter.id,
              ),
            );
      }
    } catch (_) {
      // ignore: best-effort client-side progress persistence
    }
  }

  Future<void> _maybeQueueNextChapter(String nextId) async {
    if (ref.read(activeDownloadsScopeIdProvider) == null) return;

    if (ref.read(preferencesProvider).wifiOnlyDownloads) {
      final onWifi = await ref.read(networkConnectivityProvider).isOnWifi();
      if (!onWifi) return;
    }

    await ref.read(downloadQueueControllerProvider.notifier).enqueueChapter(
          id: (
            sourceId: widget.sourceId,
            seriesKey: widget.seriesId,
            chapterKey: nextId,
          ),
        );
  }

  @override
  Widget build(BuildContext context) {
    final key = (
      sourceId: widget.sourceId,
      seriesId: widget.seriesId,
      chapterId: widget.chapterId,
    );
    final chapterAsync = ref.watch(sourceReaderChapterProvider(key));
    // Watched, never awaited (spec R3): a chapter served from disk knows its
    // pages but not its neighbours, and waiting on the network to learn them
    // would put the network back in front of first paint.
    final neighbours = ref.watch(sourceChapterNeighboursProvider(key)).valueOrNull;
    final readAllOrder = widget.readAll
        ? ref
            .watch(
              seriesReadingOrderProvider(
                (sourceId: widget.sourceId, seriesId: widget.seriesId),
              ),
            )
            .valueOrNull
        : null;

    void retry() {
      // The payload is its own cache entry — invalidating only the resolved
      // provider would re-read the stored error and the button would do
      // nothing.
      ref.invalidate(sourceReaderPayloadProvider(key));
      ref.invalidate(sourceReaderChapterProvider(key));
    }

    return chapterAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: retry,
          onBack: () => context.go(
            RoutePaths.sourceSeriesDetail(widget.sourceId, widget.seriesId),
          ),
        );
      },
      data: (chapter) {
        if (chapter.pages.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(
              message: 'This chapter has no pages.',
            ),
            onRetry: retry,
            onBack: () => context.go(
              RoutePaths.sourceSeriesDetail(widget.sourceId, widget.seriesId),
            ),
          );
        }

        final previousChapterId =
            chapter.previousChapterId ?? neighbours?.previousChapterId;
        final nextChapterId = chapter.nextChapterId ?? neighbours?.nextChapterId;

        // Guarded on the id being *known*, not merely on the chapter having
        // been shown: a downloaded chapter paints from disk before anything
        // knows what comes next, and the eager queue must still fire once the
        // neighbours land rather than being marked done against a null.
        if (nextChapterId != null && _prefetchedFor != widget.chapterId) {
          _prefetchedFor = widget.chapterId;
          // Deferred past this build, like every other one-shot side effect
          // triggered from a build method in this codebase (see
          // OpenChapterScope._claim) — reading providers is safe mid-build,
          // but a network/DB-touching side effect belongs after it.
          WidgetsBinding.instance.addPostFrameCallback(
            (_) => unawaited(_maybeQueueNextChapter(nextChapterId)),
          );
        }

        final feedController = _feedFor(
          chapter,
          previousChapterId: previousChapterId,
          nextChapterId: nextChapterId,
        );
        if (readAllOrder != null && readAllOrder.isNotEmpty) {
          feedController.setOrder(readAllOrder);
        }
        // The edge prompts belong to the chapters at the FEED's edges, not to
        // the one the route opened at. A Read-all window that has slid on has
        // left the anchor far behind, and offering its neighbour as the way out
        // of a stalled run walks the reader back to where they started.
        final beforeFeed = feedController.previousBeforeFeed;
        final beyondFeed = feedController.nextBeyondFeed;

        return OpenChapterScope(
          chapterId: (
            sourceId: widget.sourceId,
            seriesKey: widget.seriesId,
            chapterKey: widget.chapterId,
          ),
          child: ReaderContent(
            key: ValueKey(
              '${widget.sourceId}:${widget.seriesId}:${widget.chapterId}',
            ),
            feed: feedController.feed,
            scrollStorageKey:
                '${widget.sourceId}:${widget.seriesId}:${widget.chapterId}',
            initialPage: widget.initialPage,
            showBookmark: false,
            onReachedFeedEnd: feedController.extendForward,
            onReachedFeedStart: feedController.extendBackward,
            onSaveProgress: _saveProgress,
            onBack: () => context.go(
              RoutePaths.sourceSeriesDetail(widget.sourceId, widget.seriesId),
            ),
            // Straight to this source's series page — the connector series id can
            // contain `/`, so the encoding in RoutePaths is what keeps it intact.
            onOpenSeries: () => openSeriesFromReader(
              context,
              sourceId: widget.sourceId,
              seriesKey: widget.seriesId,
            ),
            onPreviousChapter: beforeFeed != null
                ? () => context.go(
                      RoutePaths.sourceReader(
                        widget.sourceId,
                        widget.seriesId,
                        beforeFeed,
                      ),
                    )
                : null,
            onNextChapter: beyondFeed != null
                ? () => context.go(
                      RoutePaths.sourceReader(
                        widget.sourceId,
                        widget.seriesId,
                        beyondFeed,
                      ),
                    )
                : null,
          ),
        );
      },
    );
  }
}
