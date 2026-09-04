import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/collections/providers/collection_sort_provider.dart';
import 'package:manhwamaniacs/features/collections/providers/collections_provider.dart';
import 'package:manhwamaniacs/features/collections/utils/collection_sorting.dart';
import 'package:manhwamaniacs/features/collections/widgets/collection_widgets.dart';
import 'package:manhwamaniacs/features/collections/widgets/collections_skeleton.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';

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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: 'Back',
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(Routes.more),
        ),
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
            color: context.colors.primary,
            onRefresh: () => ref.read(collectionsProvider.notifier).refresh(),
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      context.space.xl2,
                      context.space.xl2,
                      context.space.xl2,
                      context.space.lg,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const HeroHeading(text: 'Collections'),
                        SizedBox(height: context.space.xs),
                        Text(
                          collections.isEmpty
                              ? 'Organize your library into custom collections.'
                              : '${collections.length} collection${collections.length == 1 ? '' : 's'}',
                          style: context.text.body.copyWith(color: context.colors.muted),
                        ),
                      ],
                    ),
                  ),
                ),
                if (collections.isNotEmpty)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: EdgeInsets.symmetric(horizontal: context.space.xl2),
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
                          SizedBox(height: context.space.md),
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
                          SizedBox(height: context.space.xl2),
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
                    padding: EdgeInsets.fromLTRB(
                      context.space.xl2,
                      0,
                      context.space.xl2,
                      context.space.xl4,
                    ),
                    sliver: SliverList.separated(
                      itemCount: filtered.length,
                      separatorBuilder: (_, __) => SizedBox(height: context.space.lg),
                      itemBuilder: (context, index) {
                        final collection = filtered[index];
                        return CollectionBannerCard(
                          collection: collection,
                          // push, not go: `go` would replace the whole stack
                          // with a two-page match and throw away the tab shell
                          // this screen was pushed over, which also costs the
                          // iOS back-swipe on the way out of Collections.
                          onTap: () => context
                              .push(RoutePaths.collectionDetail(collection.id)),
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
        padding: EdgeInsets.all(context.space.xl2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              error.userMessage,
              style: context.text.body.copyWith(color: context.colors.danger),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: context.space.lg),
            FilledButton(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}