import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/network/network_connectivity.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_provider.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/utils/local_reader_handoff.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_series_download_status_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';

/// How many upcoming chapters to eagerly download while the reader is open.
const _autoQueueAhead = 2;

/// Online source chapter reader.
///
/// Reuses [ReaderContent] for the full reading experience (fullscreen, zoom,
/// virtualization, image cache, auto-next). Online chapters have no local
/// series, so progress is persisted client-side via [sourceProgressProvider]
/// (the shared cross-platform contract) rather than the library progress API.
///
/// While a chapter is open the reader also eagerly queues the next
/// [_autoQueueAhead] chapters for download so reading can continue offline —
/// but only on Wi-Fi (quietly checked, never prompting) and only for chapters
/// not already queued/downloading/completed.
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
  /// Chapters whose auto-download has already been handled this session, so the
  /// queue fires at most once per chapter open (not on every rebuild).
  final Set<String> _autoQueueHandled = {};

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
    } catch (_) {
      // ignore: best-effort client-side progress persistence
    }
  }

  /// Compute and queue the next [_autoQueueAhead] chapters after [chapterId].
  /// No-op when off Wi-Fi (silently) or when there is nothing fresh to queue.
  ///
  /// Entirely best-effort: eager prefetch must never surface into the reader,
  /// so a failed chapter-list fetch, connectivity check or queue call is
  /// swallowed rather than crashing the reading experience.
  Future<void> _autoQueueNext(String chapterId) async {
    try {
      final detail = await ref.read(
        sourceSeriesDetailProvider(
          (sourceId: widget.sourceId, seriesId: widget.seriesId),
        ).future,
      );
      if (!mounted) return;

      // Order ascending by chapter number (nulls last) to find what comes next.
      final ordered = [...detail.chapters]..sort((a, b) {
          final an = a.number;
          final bn = b.number;
          if (an == null && bn == null) return 0;
          if (an == null) return 1;
          if (bn == null) return -1;
          return an.compareTo(bn);
        });
      final index = ordered.indexWhere((c) => c.id == chapterId);
      if (index < 0) return;
      final upcoming = ordered
          .skip(index + 1)
          .take(_autoQueueAhead)
          .toList(growable: false);
      if (upcoming.isEmpty) return;

      // Quiet Wi-Fi gate: skip auto-queue entirely off Wi-Fi. Mirrors
      // checkWifiForDownload but runs off the widget's WidgetRef and never
      // prompts, so an automatic queue can never show the blocking Wi-Fi dialog.
      if (ref.read(wifiOnlyDownloadsProvider)) {
        final onWifi = await ref.read(networkConnectivityProvider).isOnWifi();
        if (!onWifi) return;
      }
      if (!mounted) return;

      final lookup = ref.read(
        sourceSeriesChapterDownloadLookupProvider(
          (sourceId: widget.sourceId, seriesId: widget.seriesId),
        ),
      );
      final chapterIds = [
        for (final chapter in upcoming)
          if (!lookup.isDownloadDisabled(chapter.id)) chapter.id,
      ];
      if (chapterIds.isEmpty) return;

      final result = await ref.read(downloadsProvider.notifier).queueChapters(
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
            chapterIds: chapterIds,
            seriesTitle: detail.series.title,
          );
      if (!mounted || result.isErr) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Downloading next chapters'),
          behavior: SnackBarBehavior.floating,
        ),
      );
    } catch (_) {
      // Best-effort prefetch — ignore any failure (chapter list unavailable,
      // ref disposed mid-flight, queue error) and leave reading unaffected.
    }
  }

  void _scheduleAutoQueue(String chapterId) {
    if (!_autoQueueHandled.add(chapterId)) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_autoQueueNext(chapterId));
    });
  }

  @override
  Widget build(BuildContext context) {
    final chapterAsync = ref.watch(
      sourceReaderChapterProvider(
        (
          sourceId: widget.sourceId,
          seriesId: widget.seriesId,
          chapterId: widget.chapterId,
        ),
      ),
    );

    return chapterAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: () => ref.invalidate(
            sourceReaderChapterProvider(
              (
                sourceId: widget.sourceId,
                seriesId: widget.seriesId,
                chapterId: widget.chapterId,
              ),
            ),
          ),
          onBack: () => context.go(
            RoutePaths.sourceSeriesDetail(widget.sourceId, widget.seriesId),
          ),
        );
      },
      data: (chapter) {
        if (chapter.mode == ReaderMode.local) {
          final librarySeriesId = int.tryParse(chapter.seriesId);
          final libraryChapterId = int.tryParse(chapter.id);
          if (librarySeriesId != null && libraryChapterId != null) {
            return LocalReaderHandoff(
              seriesId: librarySeriesId,
              chapterId: libraryChapterId,
              initialPage: widget.initialPage,
            );
          }
        }

        if (chapter.pages.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(
              message: 'This chapter has no pages.',
            ),
            onRetry: () => ref.invalidate(
              sourceReaderChapterProvider((
                sourceId: widget.sourceId,
                seriesId: widget.seriesId,
                chapterId: widget.chapterId,
              ),),
            ),
            onBack: () => context.go(
              RoutePaths.sourceSeriesDetail(widget.sourceId, widget.seriesId),
            ),
          );
        }

        // Eagerly download the next chapters (once per chapter open).
        _scheduleAutoQueue(widget.chapterId);

        return ReaderContent(
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
          onPreviousChapter: chapter.previousChapterId != null
              ? () => context.go(
                    RoutePaths.sourceReader(
                      widget.sourceId,
                      widget.seriesId,
                      chapter.previousChapterId!,
                    ),
                  )
              : null,
          onNextChapter: chapter.nextChapterId != null
              ? () => context.go(
                    RoutePaths.sourceReader(
                      widget.sourceId,
                      widget.seriesId,
                      chapter.nextChapterId!,
                    ),
                  )
              : null,
        );
      },
    );
  }
}
