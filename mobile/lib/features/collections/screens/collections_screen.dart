import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/collections/providers/collection_sort_provider.dart';
import 'package:aistudio_mobile/features/collections/providers/collections_provider.dart';
import 'package:aistudio_mobile/features/collections/utils/collection_sorting.dart';
import 'package:aistudio_mobile/features/collections/widgets/collection_widgets.dart';
import 'package:aistudio_mobile/features/collections/widgets/collections_skeleton.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class CollectionsScreen extends ConsumerStatefulWidget {
  const CollectionsScreen({super.key});

  @override
  ConsumerState<CollectionsScreen> createState() => _CollectionsScreenState();
}

class _CollectionsScreenState extends ConsumerState<CollectionsScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _openCreateDialog() async {
    final notifier = ref.read(collectionsProvider.notifier);
    await CollectionFormDialog.showCreate(
      context,
      onCreate: (name, description) =>
          notifier.createCollection(name: name, description: description),
    );
  }

  @override
  Widget build(BuildContext context) {
    final collectionsAsync = ref.watch(collectionsProvider);
    final sort = ref.watch(collectionSortProvider);
    final search = ref.watch(collectionSearchProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Collections'),
        actions: [
          IconButton(
            tooltip: 'New Collection',
            onPressed: _openCreateDialog,
            icon: const Icon(Icons.add),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreateDialog,
        icon: const Icon(Icons.add),
        label: const Text('New'),
      ),
      body: collectionsAsync.when(
        loading: () => const CollectionsSkeleton(),
        error: (error, _) => _CollectionsError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.read(collectionsProvider.notifier).refresh(),
        ),
        data: (collections) {
          final filtered = sortCollections(
            filterCollections(collections, search),
            sort,
          );

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: () => ref.read(collectionsProvider.notifier).refresh(),
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(
                      AppSpacing.xl2,
                      AppSpacing.xl2,
                      AppSpacing.xl2,
                      AppSpacing.lg,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Collections',
                          style: AppTypography.displayMd,
                        ),
                        const SizedBox(height: AppSpacing.xs),
                        Text(
                          collections.isEmpty
                              ? 'Organize your library into custom collections.'
                              : '${collections.length} collection${collections.length == 1 ? '' : 's'}',
                          style: AppTypography.body.copyWith(color: AppColors.muted),
                        ),
                      ],
                    ),
                  ),
                ),
                if (collections.isNotEmpty)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
                      child: Column(
                        children: [
                          TextField(
                            controller: _searchController,
                            decoration: const InputDecoration(
                              prefixIcon: Icon(Icons.search),
                              hintText: 'Search collections…',
                            ),
                            onChanged: (value) =>
                                ref.read(collectionSearchProvider.notifier).state = value,
                          ),
                          const SizedBox(height: AppSpacing.md),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: PopupMenuButton<CollectionSort>(
                              initialValue: sort,
                              onSelected: (value) =>
                                  ref.read(collectionSortProvider.notifier).state = value,
                              itemBuilder: (context) => CollectionSort.values
                                  .map(
                                    (value) => PopupMenuItem(
                                      value: value,
                                      child: Text(collectionSortLabel(value)),
                                    ),
                                  )
                                  .toList(),
                              child: Chip(
                                avatar: const Icon(Icons.sort, size: 16),
                                label: Text(collectionSortLabel(sort)),
                              ),
                            ),
                          ),
                          const SizedBox(height: AppSpacing.xl2),
                        ],
                      ),
                    ),
                  ),
                if (collections.isEmpty)
                  SliverFillRemaining(
                    hasScrollBody: false,
                    child: EmptyState(
                      icon: Icons.collections_bookmark_outlined,
                      message: 'No collections yet',
                      subtitle:
                          'Create collections to group your series by theme, mood, or reading list.',
                      action: FilledButton.icon(
                        onPressed: _openCreateDialog,
                        icon: const Icon(Icons.add),
                        label: const Text('Create your first collection'),
                      ),
                    ),
                  )
                else if (filtered.isEmpty)
                  const SliverFillRemaining(
                    hasScrollBody: false,
                    child: EmptyState(
                      icon: Icons.search_off,
                      message: 'No collections match your search',
                      subtitle: 'Try a different term or clear the search.',
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
                      itemCount: filtered.length,
                      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.lg),
                      itemBuilder: (context, index) {
                        final collection = filtered[index];
                        return CollectionBannerCard(
                          collection: collection,
                          onTap: () => context.go(RoutePaths.collectionDetail(collection.id)),
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
}

class _CollectionsError extends StatelessWidget {
  const _CollectionsError({
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
          ],
        ),
      ),
    );
  }
}
