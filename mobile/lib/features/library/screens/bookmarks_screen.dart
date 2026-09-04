import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
import 'package:manhwamaniacs/features/novels/utils/novel_book.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/glass_card.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

class BookmarksScreen extends ConsumerWidget {
  const BookmarksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bookmarksAsync = ref.watch(bookmarksProvider);
    final scope = ref.watch(contentModeScopeProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        title: const Text('Bookmarks'),
      ),
      body: bookmarksAsync.when(
        loading: () => ListView(
          padding: EdgeInsets.all(context.space.xl2),
          children: [
            const SkeletonBox(width: double.infinity, height: 100),
            SizedBox(height: context.space.md),
            const SkeletonBox(width: double.infinity, height: 100),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load bookmarks.',
                style: context.text.body.copyWith(color: context.colors.danger),
              ),
              SizedBox(height: context.space.lg),
              FilledButton(
                onPressed: () => ref.invalidate(bookmarksProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) {
          final bookmarks = scope.filter(data.bookmarks, (b) => b.sourceId);
          return RefreshIndicator(
          color: context.colors.primary,
          onRefresh: () async => ref.read(bookmarksProvider.notifier).refresh(),
          child: ListView(
            padding: EdgeInsets.all(context.space.xl2),
            children: [
              const HeroHeading(text: 'Bookmarks'),
              SizedBox(height: context.space.xs),
              Text(
                'Jump back to exactly where you were, or remove ones you no '
                'longer need.',
                style: context.text.body.copyWith(color: context.colors.muted),
              ),
              SizedBox(height: context.space.xl2),
              if (bookmarks.isEmpty)
                const EmptyState(
                  icon: Icons.bookmark_border,
                  message: 'No bookmarks yet',
                  subtitle: 'Tap the bookmark icon in either reader to save '
                      'the exact spot you are on.',
                )
              else
                ...bookmarks.map(
                  (bookmark) => Padding(
                    padding: EdgeInsets.only(bottom: context.space.md),
                    child: _BookmarkCard(
                      bookmark: bookmark,
                      actionPending: data.actionPending,
                    ),
                  ),
                ),
            ],
          ),
          );
        },
      ),
    );
  }
}

/// How far through the chapter a bookmark sits, in the words the design asked
/// for: "62% of chapter 14".
///
/// Degrades in two steps rather than lying. Without a chapter number the
/// chapter cannot be named, so it is "62% through this chapter"; without a
/// unit count there is no percentage at all — an old page-only bookmark
/// migrated from before this design says "page 4" and nothing more, because
/// claiming it was 0% of the way in would be inventing a fact.
String bookmarkPositionLabel(Bookmark bookmark) {
  final percent = bookmark.positionPercent;
  final number = bookmark.chapterNumber;
  if (percent == null) {
    return bookmark.mediaType.isNovel
        ? 'Paragraph ${bookmark.anchorIndex}'
        : 'Page ${bookmark.anchorIndex}';
  }
  if (number == null) return '$percent% through this chapter';
  return '$percent% of chapter ${formatChapterNumber(number)}';
}

class _BookmarkCard extends ConsumerWidget {
  const _BookmarkCard({
    required this.bookmark,
    required this.actionPending,
  });

  final Bookmark bookmark;
  final bool actionPending;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final created = DateFormat.yMMMd().add_jm().format(
          bookmark.createdAt.toLocal(),
        );
    // The row's own medium, not a lookup through the sources listing: a phone
    // with no signal has no listing, and the reader that captured the
    // position is the only thing that knew for certain which surface it came
    // off.
    final isNovel = bookmark.mediaType.isNovel;
    final title = (bookmark.seriesTitle?.trim().isNotEmpty ?? false)
        ? bookmark.seriesTitle!
        : chapterLabel(
            number: bookmark.chapterNumber,
            title: bookmark.chapterKey,
          ).primary;
    // Tapping opens the reader AT the position, not at the chapter start —
    // that is the whole point of storing a fraction.
    final readerPath = isNovel
        ? RoutePaths.novelReaderAt(
            bookmark.sourceId,
            bookmark.seriesKey,
            bookmark.chapterKey,
            paragraph: bookmark.anchorIndex,
            fraction: bookmark.anchorFraction,
          )
        : RoutePaths.readerAt(
            bookmark.sourceId,
            bookmark.seriesKey,
            bookmark.chapterKey,
            page: bookmark.anchorIndex,
            fraction: bookmark.anchorFraction,
          );
    final snippet = bookmark.snippet?.trim();

    return GlassCard(
      onTap: () => context.push(readerPath),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: context.text.labelLg),
                SizedBox(height: context.space.xs),
                Text(
                  bookmark.sourceId,
                  style: context.text.body.copyWith(color: context.colors.muted),
                ),
                SizedBox(height: context.space.xs),
                Row(
                  children: [
                    Icon(
                      isNovel
                          ? Icons.menu_book_rounded
                          : Icons.auto_stories_rounded,
                      size: 14,
                      color: context.colors.muted,
                    ),
                    SizedBox(width: context.space.xs),
                    Flexible(
                      child: Text(
                        bookmarkPositionLabel(bookmark),
                        style: context.text.caption
                            .copyWith(color: context.colors.muted),
                      ),
                    ),
                  ],
                ),
                // A prose bookmark has no cover and no page image; the words
                // at that exact spot are the only thing that tells it apart
                // from every other bookmark in the same chapter.
                if (isNovel && snippet != null && snippet.isNotEmpty) ...[
                  SizedBox(height: context.space.sm),
                  Text(
                    snippet,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: context.text.body.copyWith(
                      fontStyle: FontStyle.italic,
                      color: context.colors.muted,
                    ),
                  ),
                ],
                if (bookmark.note != null && bookmark.note!.isNotEmpty) ...[
                  SizedBox(height: context.space.xs),
                  Text(bookmark.note!, style: context.text.body),
                ],
                SizedBox(height: context.space.xs),
                Text(
                  created,
                  style:
                      context.text.caption.copyWith(color: context.colors.muted),
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Remove bookmark',
            onPressed: actionPending
                ? null
                : () => ref
                    .read(bookmarksProvider.notifier)
                    .deleteBookmark(bookmark),
          ),
        ],
      ),
    );
  }
}
