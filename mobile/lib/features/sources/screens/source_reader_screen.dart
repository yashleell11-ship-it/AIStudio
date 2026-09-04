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
  });

  final String sourceId;
  final String seriesId;
  final String chapterId;
  final int initialPage;

  @override
  ConsumerState<SourceReaderScreen> createState() => _SourceReaderScreenState();
}

class _SourceReaderScreenState extends ConsumerState<SourceReaderScreen> {
  /// Guards the eager next-chapter queue so it fires once per chapter shown,
  /// not on every unrelated rebuild of this widget.
  String? _prefetchedFor;

  Future<void> _saveProgress(int page, int pageCount) async {
    // ReaderContent flushes progress from its dispose(), by which point this
    // state (and its ref/context) may already be deactivated — swallow that
    // race so a normal reader teardown never throws.
    try {
      await ref.read(sourceProgressProvider.notifier).record(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            chapterId: widget.chapterId,
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
                chapterKey: widget.chapterId,
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
            chapter: chapter,
            scrollStorageKey:
                '${widget.sourceId}:${widget.seriesId}:${widget.chapterId}',
            initialPage: widget.initialPage,
            showBookmark: false,
            onSaveProgress: (page) => _saveProgress(page, chapter.pageCount),
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
            onPreviousChapter: previousChapterId != null
                ? () => context.go(
                      RoutePaths.sourceReader(
                        widget.sourceId,
                        widget.seriesId,
                        previousChapterId,
                      ),
                    )
                : null,
            onNextChapter: nextChapterId != null
                ? () => context.go(
                      RoutePaths.sourceReader(
                        widget.sourceId,
                        widget.seriesId,
                        nextChapterId,
                      ),
                    )
                : null,
          ),
        );
      },
    );
  }
}
