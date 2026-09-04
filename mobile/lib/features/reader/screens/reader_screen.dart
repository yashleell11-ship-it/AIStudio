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
  });

  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final int initialPage;

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
          ),
        );
      },
    );
  }
}

class _ManifestReaderBody extends ConsumerWidget {
  const _ManifestReaderBody({
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.resolved,
    required this.neighbours,
    required this.initialPage,
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

  String? get _prev => resolved.prev ?? neighbours?.prev;
  String? get _next => resolved.next ?? neighbours?.next;

  /// The number progress is filed under. The store stamps it at download time
  /// from the same manifest, so the two agree; the manifest wins only when the
  /// store had none to stamp.
  double? get _chapterNumber => resolved.chapterNumber ?? neighbours?.chapterNumber;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final repo = ref.read(readerRepositoryProvider);
    // Resolved once here rather than via `ref.read(...)` inside the
    // callbacks below: `ReaderContent.dispose()` flushes a pending progress
    // save, and by then this widget's own element may already be
    // deactivated — reading a provider through it at that point throws
    // ("Looking up a deactivated widget's ancestor is unsafe"). Plain
    // objects captured here stay safe to call from anywhere.
    final progressOutbox = ref.read(progressOutboxControllerProvider);
    final downloadsStore = ref.read(downloadsStoreProvider);
    final ReaderChapter readerChapter = resolved.chapter;
    final id = (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

    return ReaderContent(
      key: ValueKey('$sourceId:$seriesKey:$chapterKey'),
      chapter: readerChapter,
      scrollStorageKey: '$sourceId:$seriesKey:$chapterKey',
      initialPage: initialPage,
      onBack: () => context.pop(),
      onOpenSeries: () => openSeriesFromReader(
        context,
        sourceId: sourceId,
        seriesKey: seriesKey,
      ),
      onPreviousChapter: _prev != null
          ? () => context.go(
                RoutePaths.reader(sourceId, seriesKey, _prev!),
              )
          : null,
      onNextChapter: _next != null
          ? () => context.go(
                RoutePaths.reader(sourceId, seriesKey, _next!),
              )
          : null,
      onSaveProgress: (page) async {
        final isCompleted = page >= readerChapter.pageCount;
        // Local-first (spec §3): every save writes to the on-device outbox
        // and is flushed best-effort — the reader never blocks on, or loses
        // a save to, a flaky or absent connection.
        await progressOutbox.save(
          ProgressPush(
            sourceId: sourceId,
            seriesKey: seriesKey,
            chapterKey: chapterKey,
            chapterNumber: _chapterNumber,
            lastPage: page,
            pageCount: readerChapter.pageCount,
            isCompleted: isCompleted,
          ),
        );
        if (isCompleted) {
          // Read-then-expire (spec §3/§3b): starts the 48h phone-copy timer.
          // A no-op if this chapter was never downloaded.
          await downloadsStore?.markRead(id);
        }
      },
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
