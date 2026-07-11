import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_page.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/page_image_url.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

class ReaderScreen extends ConsumerWidget {
  const ReaderScreen({
    super.key,
    required this.seriesId,
    required this.chapterId,
    this.initialPage = 1,
  });

  final int seriesId;
  final int chapterId;
  final int initialPage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final chapterAsync = ref.watch(readerChapterProvider(chapterId));

    return chapterAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: () => ref.invalidate(readerChapterProvider(chapterId)),
          onBack: () => context.pop(),
        );
      },
      data: (chapter) {
        if (chapter.pages.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(message: 'This chapter has no pages.'),
            onRetry: () => ref.invalidate(readerChapterProvider(chapterId)),
            onBack: () => context.pop(),
          );
        }

        return _LocalReaderBody(
          seriesId: seriesId,
          chapterId: chapterId,
          chapter: chapter,
          initialPage: initialPage,
        );
      },
    );
  }
}

class _LocalReaderBody extends ConsumerWidget {
  const _LocalReaderBody({
    required this.seriesId,
    required this.chapterId,
    required this.chapter,
    required this.initialPage,
  });

  final int seriesId;
  final int chapterId;
  final ChapterDetail chapter;
  final int initialPage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final previousAsync = ref.watch(
      adjacentChapterProvider((chapterId: chapterId, direction: 'previous')),
    );
    final nextAsync = ref.watch(
      adjacentChapterProvider((chapterId: chapterId, direction: 'next')),
    );
    final previousChapter = previousAsync.valueOrNull;
    final nextChapter = nextAsync.valueOrNull;
    final repo = ref.read(libraryRepositoryProvider);
    final apiBaseUrl = ref.read(apiBaseUrlProvider);

    final readerChapter = ReaderChapter(
      id: chapter.id.toString(),
      seriesId: chapter.seriesId.toString(),
      title: chapter.title,
      pageCount: chapter.pageCount,
      mode: ReaderMode.local,
      pages: chapter.pages
          .map(
            (page) => ReaderPage(
              id: page.id.toString(),
              number: page.number,
              imageUrl: readerPageImageUrl(apiBaseUrl, page.id),
            ),
          )
          .toList(),
    );

    return ReaderContent(
      key: ValueKey(chapterId.toString()),
      chapter: readerChapter,
      scrollStorageKey: chapterId.toString(),
      initialPage: initialPage,
      onBack: () => context.pop(),
      onPreviousChapter: previousChapter != null
          ? () => context.go(RoutePaths.reader(seriesId, previousChapter.id))
          : null,
      onNextChapter: nextChapter != null
          ? () => context.go(RoutePaths.reader(seriesId, nextChapter.id))
          : null,
      onSaveProgress: (page) => repo.saveProgress(
        seriesId: seriesId,
        chapterId: chapterId,
        lastPage: page,
      ).then((_) {}),
      onAddBookmark: (page) => repo
          .addBookmark(
            seriesId: seriesId,
            chapterId: chapterId,
            page: page,
          )
          .then((result) => result.isOk),
    );
  }
}