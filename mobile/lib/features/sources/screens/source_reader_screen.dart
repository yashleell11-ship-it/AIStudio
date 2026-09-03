import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_series_navigation.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/features/sources/providers/source_progress_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';

/// Online source chapter reader.
///
/// Reuses [ReaderContent] for the full reading experience (fullscreen, zoom,
/// virtualization, image cache, auto-next). Online chapters have no local
/// series, so progress is persisted client-side via [sourceProgressProvider]
/// (the shared cross-platform contract) rather than the library progress API.
///
// TODO(1c-M3): re-add eager next-chapter download queuing (was gated on
// Wi-Fi and the now-deleted server download queue) once the on-device store
// ships.
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
          // Straight to this source's series page — the connector series id can
          // contain `/`, so the encoding in RoutePaths is what keeps it intact.
          onOpenSeries: () => openSourceSeriesFromReader(
            context,
            sourceId: widget.sourceId,
            seriesId: widget.seriesId,
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
