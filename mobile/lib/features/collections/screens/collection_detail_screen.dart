import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/collections/providers/collection_detail_provider.dart';
import 'package:aistudio_mobile/features/collections/widgets/add_series_dialog.dart';
import 'package:aistudio_mobile/features/collections/widgets/collection_widgets.dart';
import 'package:aistudio_mobile/features/collections/widgets/collections_skeleton.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/utils/cover_url.dart';
import 'package:aistudio_mobile/features/library/widgets/library/series_grid.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class CollectionDetailScreen extends ConsumerWidget {
  const CollectionDetailScreen({super.key, required this.collectionId});

  final int collectionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final detailAsync = ref.watch(collectionDetailProvider(collectionId));
    final apiBaseUrl = ref.watch(apiBaseUrlProvider);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.collections),
        ),
        title: detailAsync.maybeWhen(
          data: (collection) => Text(collection.name),
          orElse: () => const Text('Collection'),
        ),
      ),
      body: detailAsync.when(
        loading: () => const CollectionDetailSkeleton(),
        error: (error, _) => _CollectionDetailError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.read(collectionDetailProvider(collectionId).notifier).refresh(),
        ),
        data: (collection) {
          final coverSeriesId =
              collection.series.items.isNotEmpty ? collection.series.items.first.id : null;

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () =>
                ref.read(collectionDetailProvider(collectionId).notifier).refresh(),
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      CollectionHeroBanner(
                        name: collection.name,
                        description: collection.description,
                        seriesCount: collection.series.total,
                        coverUrl: collectionCoverUrl(collection.coverPath),
                        coverSeriesId: coverSeriesId,
                        apiBaseUrl: apiBaseUrl,
                      ),
                      Padding(
                        padding: const EdgeInsets.all(AppSpacing.xl2),
                        child: Wrap(
                          spacing: AppSpacing.sm,
                          runSpacing: AppSpacing.sm,
                          children: [
                            OutlinedButton.icon(
                              onPressed: () => _openAddSeriesDialog(context, ref, collection),
                              icon: const Icon(Icons.add, size: 16),
                              label: const Text('Add Series'),
                            ),
                            OutlinedButton.icon(
                              onPressed: () => _openRenameDialog(context, ref, collection),
                              icon: const Icon(Icons.edit_outlined, size: 16),
                              label: const Text('Rename'),
                            ),
                            TextButton.icon(
                              onPressed: () => _confirmDelete(context, ref),
                              icon: const Icon(Icons.delete_outline, size: 16),
                              label: const Text('Delete'),
                              style: TextButton.styleFrom(foregroundColor: AppColors.danger),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                if (collection.series.items.isEmpty)
                  SliverFillRemaining(
                    hasScrollBody: false,
                    child: EmptyState(
                      icon: Icons.menu_book_outlined,
                      message: 'This collection is empty',
                      subtitle: 'Add series from your library to start building this collection.',
                      action: FilledButton.icon(
                        onPressed: () => _openAddSeriesDialog(context, ref, collection),
                        icon: const Icon(Icons.add),
                        label: const Text('Add series'),
                      ),
                    ),
                  )
                else
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.xl2,
                      0,
                      AppSpacing.xl2,
                      AppSpacing.xl4,
                    ),
                    sliver: SliverToBoxAdapter(
                      child: SeriesGrid(
                        items: collection.series.items,
                        viewMode: LibraryViewMode.grid,
                        onSeriesTap: (series) => context.push(RoutePaths.seriesDetail(series.id)),
                        onToggleFavorite: (seriesId) async {
                          final repo = ref.read(libraryRepositoryProvider);
                          await repo.toggleFavorite(seriesId);
                          await ref
                              .read(collectionDetailProvider(collectionId).notifier)
                              .refresh();
                        },
                        onRemoveSeries: (seriesId) async {
                          final confirmed = await showDialog<bool>(
                            context: context,
                            builder: (context) => AlertDialog(
                              title: const Text('Remove series?'),
                              content: const Text(
                                'This series will be removed from the collection but stay in your library.',
                              ),
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.of(context).pop(false),
                                  child: const Text('Cancel'),
                                ),
                                FilledButton(
                                  onPressed: () => Navigator.of(context).pop(true),
                                  child: const Text('Remove'),
                                ),
                              ],
                            ),
                          );
                          if (confirmed != true || !context.mounted) return;
                          await ref
                              .read(collectionDetailProvider(collectionId).notifier)
                              .removeSeries(seriesId);
                        },
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

  Future<void> _openAddSeriesDialog(
    BuildContext context,
    WidgetRef ref,
    CollectionDetail collection,
  ) async {
    await showDialog<void>(
      context: context,
      builder: (context) => AddSeriesDialog(
        existingSeriesIds: collection.series.items.map((item) => item.id).toSet(),
        onAdd: (seriesId) => ref
            .read(collectionDetailProvider(collectionId).notifier)
            .addSeries(seriesId),
      ),
    );
  }

  Future<void> _openRenameDialog(
    BuildContext context,
    WidgetRef ref,
    CollectionDetail collection,
  ) async {
    await CollectionFormDialog.showRename(
      context,
      initialName: collection.name,
      initialDescription: collection.description,
      onRename: (name, description) => ref
          .read(collectionDetailProvider(collectionId).notifier)
          .updateCollection(name: name, description: description),
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete collection?'),
        content: const Text('Series will not be removed from your library.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.danger),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    final error = await ref
        .read(collectionDetailProvider(collectionId).notifier)
        .deleteCollection();
    if (!context.mounted) return;
    if (error == null) {
      context.go(Routes.collections);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.userMessage)),
      );
    }
  }
}

class _CollectionDetailError extends StatelessWidget {
  const _CollectionDetailError({
    required this.error,
    required this.onRetry,
  });

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.danger),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(onPressed: onRetry, child: const Text('Retry')),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              onPressed: () => context.go(Routes.collections),
              child: const Text('Back to collections'),
            ),
          ],
        ),
      ),
    );
  }
}
