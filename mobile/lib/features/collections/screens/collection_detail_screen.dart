import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/collections/providers/collection_detail_provider.dart';
import 'package:manhwamaniacs/features/collections/widgets/add_series_dialog.dart';
import 'package:manhwamaniacs/features/collections/widgets/collection_widgets.dart';
import 'package:manhwamaniacs/features/collections/widgets/collections_skeleton.dart';
import 'package:manhwamaniacs/features/library/models/collection_detail.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

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
          final coverSeriesRef = collection.series.isNotEmpty
              ? (collection.series.first.sourceId, collection.series.first.seriesKey)
              : null;

          return RefreshIndicator(
            color: context.colors.primary,
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
                        seriesCount: collection.seriesCount,
                        coverUrl: collectionCoverUrl(collection.coverUrl),
                        coverSeriesRef: coverSeriesRef,
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
                              style: TextButton.styleFrom(foregroundColor: context.colors.danger),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                if (collection.series.isEmpty)
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
                    sliver: SliverList.separated(
                      itemCount: collection.series.length,
                      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                      itemBuilder: (context, index) {
                        final member = collection.series[index];
                        return _CollectionSeriesTile(
                          sourceId: member.sourceId,
                          seriesKey: member.seriesKey,
                          apiBaseUrl: apiBaseUrl,
                          onTap: () => context.push(
                            RoutePaths.sourceSeriesDetail(member.sourceId, member.seriesKey),
                          ),
                          onRemove: () async {
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
                                .removeSeries(
                                  sourceId: member.sourceId,
                                  seriesKey: member.seriesKey,
                                );
                          },
                        );
                      },
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
        existingSeriesKeys: collection.series
            .map((member) => seriesCompositeKey(member.sourceId, member.seriesKey))
            .toSet(),
        onAdd: (series) => ref
            .read(collectionDetailProvider(collectionId).notifier)
            .addSeries(sourceId: series.sourceId, seriesKey: series.seriesKey),
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
            style: FilledButton.styleFrom(backgroundColor: context.colors.danger),
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
      // The collection this screen renders no longer exists, so unwind to the
      // list. Pop when there is a stack to pop (the normal path in from More)
      // and only fall back to a location change on a cold deep link.
      context.canPop() ? context.pop() : context.go(Routes.collections);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.userMessage)),
      );
    }
  }
}

/// One collection member row. Collection membership carries no title/cover of
/// its own — only the opaque `(sourceId, seriesKey)` pointer — so the cover is
/// resolved through the source proxy and the identity itself stands in for a
/// title until the row is opened on the source series page.
class _CollectionSeriesTile extends StatelessWidget {
  const _CollectionSeriesTile({
    required this.sourceId,
    required this.seriesKey,
    required this.apiBaseUrl,
    required this.onTap,
    required this.onRemove,
  });

  final String sourceId;
  final String seriesKey;
  final String apiBaseUrl;
  final VoidCallback onTap;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: context.colors.panel,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              SizedBox(
                width: 44,
                height: 66,
                child: SeriesCoverImage(
                  url: sourceSeriesCoverUrl(apiBaseUrl, sourceId, seriesKey),
                  borderRadius: 8,
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      seriesKey,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.labelLg,
                    ),
                    Text(
                      sourceId,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.caption.copyWith(color: context.colors.muted),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: onRemove,
                icon: Icon(Icons.remove_circle_outline, color: context.colors.danger),
                tooltip: 'Remove from collection',
              ),
            ],
          ),
        ),
      ),
    );
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
              style: AppTypography.body.copyWith(color: context.colors.danger),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.lg),
            FilledButton(onPressed: onRetry, child: const Text('Retry')),
            const SizedBox(height: AppSpacing.md),
            OutlinedButton(
              onPressed: () =>
                  context.canPop() ? context.pop() : context.go(Routes.collections),
              child: const Text('Back to collections'),
            ),
          ],
        ),
      ),
    );
  }
}