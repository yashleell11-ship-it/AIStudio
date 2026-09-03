import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:manhwamaniacs/features/reader/providers/reader_chapter_provider.dart';
import 'package:manhwamaniacs/features/reader/utils/reader_series_navigation.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_content.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_error_state.dart';
import 'package:manhwamaniacs/features/reader/widgets/reader_skeleton.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

/// The manifest-driven reader for a followed series' chapter — the one
/// reader every non-source-browsing entry point (series detail, continue
/// reading, bookmarks, history) links to. Identity is the opaque
/// `(sourceId, seriesKey, chapterKey)` triple; see [Routes.reader].
class ReaderScreen extends ConsumerWidget {
  const ReaderScreen({
    super.key,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    this.initialPage = 1,
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final int initialPage;

  ChapterManifestKey get _key =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final manifestAsync = ref.watch(chapterManifestProvider(_key));

    return manifestAsync.when(
      loading: () => const ReaderSkeleton(),
      error: (error, _) {
        final appError = error is AppError
            ? error
            : UnknownError(message: error.toString(), cause: error);
        return ReaderErrorState(
          error: appError,
          onRetry: () => ref.invalidate(chapterManifestProvider(_key)),
          onBack: () => context.pop(),
        );
      },
      data: (manifest) {
        if (manifest.pages.isEmpty) {
          return ReaderErrorState(
            error: const UnknownError(message: 'This chapter has no pages.'),
            onRetry: () => ref.invalidate(chapterManifestProvider(_key)),
            onBack: () => context.pop(),
          );
        }

        return _ManifestReaderBody(
          sourceId: sourceId,
          seriesKey: seriesKey,
          manifest: manifest,
          initialPage: initialPage,
        );
      },
    );
  }
}

class _ManifestReaderBody extends ConsumerWidget {
  const _ManifestReaderBody({
    required this.sourceId,
    required this.seriesKey,
    required this.manifest,
    required this.initialPage,
  });

  final String sourceId;
  final String seriesKey;
  final ChapterManifest manifest;
  final int initialPage;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.read(readerRepositoryProvider);
    final apiBaseUrl = ref.read(apiBaseUrlProvider);
    final chapterKey = manifest.chapterKey;
    final readerChapter = manifest.toReaderChapter(apiBaseUrl);

    return ReaderContent(
      key: ValueKey('$sourceId:$seriesKey:$chapterKey'),
      chapter: readerChapter,
      scrollStorageKey: '$sourceId:$seriesKey:$chapterKey',
      initialPage: initialPage,
      onBack: () => context.pop(),
      onOpenSeries: () => openSourceSeriesFromReader(
        context,
        sourceId: sourceId,
        seriesId: seriesKey,
      ),
      onPreviousChapter: manifest.prev != null
          ? () => context.go(
                RoutePaths.reader(sourceId, seriesKey, manifest.prev!),
              )
          : null,
      onNextChapter: manifest.next != null
          ? () => context.go(
                RoutePaths.reader(sourceId, seriesKey, manifest.next!),
              )
          : null,
      onSaveProgress: (page) => repo
          .saveProgress(
            ProgressPush(
              sourceId: sourceId,
              seriesKey: seriesKey,
              chapterKey: chapterKey,
              chapterNumber: manifest.chapterNumber,
              lastPage: page,
              pageCount: manifest.pageCount,
              isCompleted: page >= manifest.pageCount,
            ),
          )
          .then((_) {}),
      onAddBookmark: (page) => repo
          .addBookmark(
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapterKey,
            page: page,
          )
          .then((result) => result.isOk),
    );
  }
}
