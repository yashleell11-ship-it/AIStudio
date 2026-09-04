import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/library/providers/bookmarks_provider.dart';
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
          padding: const EdgeInsets.all(AppSpacing.xl2),
          children: const [
            SkeletonBox(width: double.infinity, height: 100),
            SizedBox(height: AppSpacing.md),
            SkeletonBox(width: double.infinity, height: 100),
          ],
        ),
        error: (error, _) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                error is AppError ? error.userMessage : 'Failed to load bookmarks.',
                style: AppTypography.body.copyWith(color: context.colors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
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
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              const HeroHeading(text: 'Bookmarks'),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Jump back into a saved page or remove ones you no longer need.',
                style: AppTypography.body.copyWith(color: context.colors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              if (bookmarks.isEmpty)
                const EmptyState(
                  icon: Icons.bookmark_border,
                  message: 'No bookmarks yet',
                  subtitle: 'Tap the bookmark icon in the reader to save your place on a page.',
                )
              else
                ...bookmarks.map(
                  (bookmark) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _BookmarkCard(
                      bookmark: bookmark,
                      actionPending: data.actionPending,
                      isNovel: scope.modeOf(bookmark.sourceId) ==
                          ContentMode.novel,
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

class _BookmarkCard extends ConsumerWidget {
  const _BookmarkCard({
    required this.bookmark,
    required this.actionPending,
    required this.isNovel,
  });

  final Bookmark bookmark;
  final bool actionPending;

  /// Which reader this row opens. A bookmark's `page` is a page number for
  /// manga and a progress bucket for a novel; both ride the same `?page=`
  /// parameter, so only the path differs.
  final bool isNovel;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final created = bookmark.createdAt != null
        ? DateFormat.yMMMd().add_jm().format(bookmark.createdAt!.toLocal())
        : null;
    final label = chapterLabel(number: null, title: bookmark.chapterKey);
    final readerPath = isNovel
        ? RoutePaths.novelReader(
            bookmark.sourceId,
            bookmark.seriesKey,
            bookmark.chapterKey,
          )
        : RoutePaths.reader(
            bookmark.sourceId,
            bookmark.seriesKey,
            bookmark.chapterKey,
          );

    return GlassCard(
      onTap: () => context.push('$readerPath?page=${bookmark.page}'),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label.primary, style: AppTypography.labelLg),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  bookmark.sourceId,
                  style: AppTypography.body.copyWith(color: context.colors.muted),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text('Page ${bookmark.page}', style: AppTypography.caption.copyWith(color: context.colors.muted)),
                if (bookmark.note != null && bookmark.note!.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(bookmark.note!, style: AppTypography.body),
                ],
                if (created != null) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(created, style: AppTypography.caption.copyWith(color: context.colors.muted)),
                ],
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.delete_outline),
            tooltip: 'Remove bookmark',
            onPressed: actionPending
                ? null
                : () => ref.read(bookmarksProvider.notifier).deleteBookmark(bookmark.id),
          ),
        ],
      ),
    );
  }
}