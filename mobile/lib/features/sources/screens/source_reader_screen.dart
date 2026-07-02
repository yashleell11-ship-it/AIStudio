import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_content.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_error_state.dart';
import 'package:aistudio_mobile/features/reader/widgets/reader_skeleton.dart';
import 'package:aistudio_mobile/features/sources/providers/source_reader_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

/// Online source chapter reader.
///
/// Reuses [ReaderContent] for the full reading experience (fullscreen, zoom,
/// virtualization, image cache, auto-next). Unlike the local reader, online
/// chapters have no local series to persist progress or bookmarks against, so
/// those callbacks stay null — matching the desktop SourceReader.
class SourceReaderScreen extends ConsumerWidget {
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
  Widget build(BuildContext context, WidgetRef ref) {
    final chapterAsync = ref.watch(
      sourceReaderChapterProvider(
        SourceReaderChapterArgs(
          sourceId: sourceId,
          seriesId: seriesId,
          chapterId: chapterId,
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
              SourceReaderChapterArgs(
                sourceId: sourceId,
                seriesId: seriesId,
                chapterId: chapterId,
              ),
            ),
          ),
          onBack: () => context.go(
            RoutePaths.sourceSeriesDetail(sourceId, seriesId),
          ),
        );
      },
      data: (chapter) {
        if (chapter.pages.isEmpty) {
          return ColoredBox(
            color: AppColors.bg,
            child: Center(
              child: Text(
                'This chapter has no pages.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
            ),
          );
        }

        return ReaderContent(
          chapter: chapter,
          scrollStorageKey: '$sourceId:$seriesId:$chapterId',
          initialPage: initialPage,
          showBookmark: false,
          onBack: () => context.go(
            RoutePaths.sourceSeriesDetail(sourceId, seriesId),
          ),
          onPreviousChapter: chapter.previousChapterId != null
              ? () => context.go(
                    RoutePaths.sourceReader(
                      sourceId,
                      seriesId,
                      chapter.previousChapterId!,
                    ),
                  )
              : null,
          onNextChapter: chapter.nextChapterId != null
              ? () => context.go(
                    RoutePaths.sourceReader(
                      sourceId,
                      seriesId,
                      chapter.nextChapterId!,
                    ),
                  )
              : null,
        );
      },
    );
  }
}
