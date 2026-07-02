import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/providers/bookmarks_provider.dart';
import 'package:aistudio_mobile/features/reader/models/bookmark.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/glass_card.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

class BookmarksScreen extends ConsumerWidget {
  const BookmarksScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final bookmarksAsync = ref.watch(bookmarksProvider);

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
                style: AppTypography.body.copyWith(color: AppColors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(
                onPressed: () => ref.invalidate(bookmarksProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
        data: (data) => RefreshIndicator(
          color: AppColors.primary,
          onRefresh: () async => ref.read(bookmarksProvider.notifier).refresh(),
          child: ListView(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            children: [
              Text('Bookmarks', style: AppTypography.displayMd),
              const SizedBox(height: AppSpacing.xs),
              Text(
                'Jump back into a saved page or remove ones you no longer need.',
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
              const SizedBox(height: AppSpacing.xl2),
              if (data.bookmarks.isEmpty)
                const EmptyState(
                  icon: Icons.bookmark_border,
                  message: 'No bookmarks yet',
                  subtitle: 'Tap the bookmark icon in the reader to save your place on a page.',
                )
              else
                ...data.bookmarks.map(
                  (bookmark) => Padding(
                    padding: const EdgeInsets.only(bottom: AppSpacing.md),
                    child: _BookmarkCard(
                      bookmark: bookmark,
                      actionPending: data.actionPending,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BookmarkCard extends ConsumerWidget {
  const _BookmarkCard({required this.bookmark, required this.actionPending});

  final Bookmark bookmark;
  final bool actionPending;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final created = DateFormat.yMMMd().add_jm().format(bookmark.createdAt.toLocal());

    return GlassCard(
      onTap: () => context.push(
        '${RoutePaths.reader(bookmark.seriesId, bookmark.chapterId)}?page=${bookmark.page}',
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(bookmark.seriesTitle ?? 'Unknown Series', style: AppTypography.labelLg),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  bookmark.chapterTitle ?? 'Unknown Chapter',
                  style: AppTypography.body.copyWith(color: AppColors.muted),
                ),
                const SizedBox(height: AppSpacing.xs),
                Text('Page ${bookmark.page}', style: AppTypography.caption),
                if (bookmark.note != null && bookmark.note!.isNotEmpty) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(bookmark.note!, style: AppTypography.body),
                ],
                const SizedBox(height: AppSpacing.xs),
                Text(created, style: AppTypography.caption.copyWith(color: AppColors.muted)),
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
