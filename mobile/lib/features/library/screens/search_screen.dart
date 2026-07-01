import 'dart:async';

import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/library_list_state.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/providers/library_list_provider.dart';
import 'package:aistudio_mobile/features/library/utils/recent_searches.dart';
import 'package:aistudio_mobile/features/library/widgets/library/library_skeleton.dart';
import 'package:aistudio_mobile/features/library/widgets/library/series_grid.dart';
import 'package:aistudio_mobile/features/library/widgets/search/search_result_card.dart';
import 'package:aistudio_mobile/features/library/widgets/search/search_suggestions.dart';
import 'package:aistudio_mobile/features/library/widgets/search/search_toolbar.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _scrollController = ScrollController();
  final _searchController = TextEditingController();
  Timer? _searchDebounce;
  var _filtersOpen = false;
  var _recentSearches = <String>[];
  String? _lastPersistedQuery;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
    _loadRecentSearches();
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    _searchController.dispose();
    super.dispose();
  }

  void _loadRecentSearches() {
    final prefs = ref.read(sharedPrefsProvider);
    setState(() => _recentSearches = readRecentSearches(prefs));
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.pixels >= position.maxScrollExtent - 320) {
      ref.read(searchListProvider.notifier).loadMore();
    }
  }

  void _updateQuery(LibraryQuery Function(LibraryQuery current) update) {
    ref.read(searchQueryProvider.notifier).state = update(
      ref.read(searchQueryProvider),
    );
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () {
      _updateQuery((query) => query.copyWith(search: value));
    });
  }

  void _applySuggestion(String value) {
    _searchController.text = value;
    _updateQuery((query) => query.copyWith(search: value));
  }

  Future<void> _persistRecentSearch(String trimmedQuery) async {
    if (trimmedQuery.length < 2 || _lastPersistedQuery == trimmedQuery) return;
    _lastPersistedQuery = trimmedQuery;
    final prefs = ref.read(sharedPrefsProvider);
    await writeRecentSearch(prefs, trimmedQuery);
    if (mounted) {
      setState(() => _recentSearches = readRecentSearches(prefs));
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(searchQueryProvider);
    final listAsync = ref.watch(searchListProvider);
    final trimmedQuery = query.search.trim();
    final hasQuery = trimmedQuery.isNotEmpty;

    ref.listen<AsyncValue<LibraryListState>>(searchListProvider, (previous, next) {
      next.whenData((state) {
        if (hasQuery && !next.isLoading && state.items.isNotEmpty) {
          _persistRecentSearch(trimmedQuery);
        }
      });
    });

    return Scaffold(
      body: listAsync.when(
        loading: () => _SearchScrollView(
          scrollController: _scrollController,
          onRefresh: () => ref.read(searchListProvider.notifier).refresh(),
          child: _SearchBody(
            query: query,
            hasQuery: hasQuery,
            resultCount: 0,
            isLoading: true,
            recentSearches: _recentSearches,
            filtersOpen: _filtersOpen,
            searchController: _searchController,
            onSearchChanged: _onSearchChanged,
            onSelectSuggestion: _applySuggestion,
            onToggleFilters: () => setState(() => _filtersOpen = !_filtersOpen),
            onFilterChanged: (filter) =>
                _updateQuery((q) => q.copyWith(filter: filter)),
            onFavoritesChanged: (favoritesOnly) =>
                _updateQuery((q) => q.copyWith(favoritesOnly: favoritesOnly)),
            onSortChanged: (sort) => _updateQuery((q) => q.copyWith(sort: sort)),
            onViewModeChanged: (viewMode) =>
                _updateQuery((q) => q.copyWith(viewMode: viewMode)),
            onSeriesTap: (series) =>
                context.push(RoutePaths.seriesDetail(series.id)),
            onToggleFavorite: (seriesId) =>
                ref.read(searchListProvider.notifier).toggleFavorite(seriesId),
          ),
        ),
        error: (error, _) => _SearchError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.read(searchListProvider.notifier).refresh(),
        ),
        data: (state) => _SearchScrollView(
          scrollController: _scrollController,
          onRefresh: () => ref.read(searchListProvider.notifier).refresh(),
          child: _SearchBody(
            query: query,
            hasQuery: hasQuery,
            resultCount: state.total,
            isLoading: false,
            state: state,
            recentSearches: _recentSearches,
            filtersOpen: _filtersOpen,
            searchController: _searchController,
            onSearchChanged: _onSearchChanged,
            onSelectSuggestion: _applySuggestion,
            onToggleFilters: () => setState(() => _filtersOpen = !_filtersOpen),
            onFilterChanged: (filter) =>
                _updateQuery((q) => q.copyWith(filter: filter)),
            onFavoritesChanged: (favoritesOnly) =>
                _updateQuery((q) => q.copyWith(favoritesOnly: favoritesOnly)),
            onSortChanged: (sort) => _updateQuery((q) => q.copyWith(sort: sort)),
            onViewModeChanged: (viewMode) =>
                _updateQuery((q) => q.copyWith(viewMode: viewMode)),
            onSeriesTap: (series) =>
                context.push(RoutePaths.seriesDetail(series.id)),
            onToggleFavorite: (seriesId) =>
                ref.read(searchListProvider.notifier).toggleFavorite(seriesId),
          ),
        ),
      ),
    );
  }
}

class _SearchBody extends StatelessWidget {
  const _SearchBody({
    required this.query,
    required this.hasQuery,
    required this.resultCount,
    required this.isLoading,
    required this.recentSearches,
    required this.filtersOpen,
    required this.searchController,
    required this.onSearchChanged,
    required this.onSelectSuggestion,
    required this.onToggleFilters,
    required this.onFilterChanged,
    required this.onFavoritesChanged,
    required this.onSortChanged,
    required this.onViewModeChanged,
    required this.onSeriesTap,
    required this.onToggleFavorite,
    this.state,
  });

  final LibraryQuery query;
  final bool hasQuery;
  final int resultCount;
  final bool isLoading;
  final LibraryListState? state;
  final List<String> recentSearches;
  final bool filtersOpen;
  final TextEditingController searchController;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String> onSelectSuggestion;
  final VoidCallback onToggleFilters;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<bool> onFavoritesChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;
  final ValueChanged<SeriesSummary> onSeriesTap;
  final ValueChanged<int> onToggleFavorite;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl2),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SearchToolbar(
            query: query,
            resultCount: resultCount,
            isSearching: hasQuery,
            searchController: searchController,
            onSearchChanged: onSearchChanged,
            onFilterChanged: onFilterChanged,
            onFavoritesChanged: onFavoritesChanged,
            onSortChanged: onSortChanged,
            onViewModeChanged: onViewModeChanged,
          ),
          if (!hasQuery) ...[
            const SizedBox(height: AppSpacing.xl2),
            SearchSuggestionsPanel(
              recentSearches: recentSearches,
              onSelect: onSelectSuggestion,
              filtersOpen: filtersOpen,
              onToggleFilters: onToggleFilters,
            ),
          ],
          if (hasQuery) ...[
            const SizedBox(height: AppSpacing.xl2),
            if (isLoading)
              SearchResultsSkeleton(viewMode: query.viewMode)
            else if (state != null && state!.isEmpty)
              const LibraryEmptyPanel(emptyState: LibraryEmptyState.search)
            else if (state != null) ...[
              if (state!.error != null) ...[
                _InlineError(message: state!.error!.userMessage),
                const SizedBox(height: AppSpacing.lg),
              ],
              if (query.viewMode == LibraryViewMode.grid)
                SeriesGrid(
                  items: state!.items,
                  viewMode: query.viewMode,
                  onSeriesTap: onSeriesTap,
                  onToggleFavorite: onToggleFavorite,
                )
              else
                Column(
                  children: [
                    for (final series in state!.items) ...[
                      SearchResultCard(
                        series: series,
                        onTap: () => onSeriesTap(series),
                        onToggleFavorite: () => onToggleFavorite(series.id),
                      ),
                      const SizedBox(height: AppSpacing.md),
                    ],
                  ],
                ),
              if (state!.isLoadingMore) ...[
                const SizedBox(height: AppSpacing.xl2),
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(AppSpacing.lg),
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                ),
              ],
            ],
          ],
          const SizedBox(height: AppSpacing.xl3),
        ],
      ),
    );
  }
}

class _SearchScrollView extends StatelessWidget {
  const _SearchScrollView({
    required this.scrollController,
    required this.onRefresh,
    required this.child,
  });

  final ScrollController scrollController;
  final Future<void> Function() onRefresh;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: onRefresh,
      color: AppColors.primary,
      child: CustomScrollView(
        controller: scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverToBoxAdapter(child: child),
        ],
      ),
    );
  }
}

class _InlineError extends StatelessWidget {
  const _InlineError({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.danger.withAlpha(26),
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.danger.withAlpha(77)),
      ),
      child: Text(
        message,
        style: AppTypography.body.copyWith(color: AppColors.danger),
      ),
    );
  }
}

class _SearchError extends StatelessWidget {
  const _SearchError({
    required this.error,
    required this.onRetry,
  });

  final AppError error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, color: AppColors.danger, size: 48),
            const SizedBox(height: AppSpacing.lg),
            Text(
              'Search failed',
              style: AppTypography.h3,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl2),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Try Again'),
            ),
          ],
        ),
      ),
    );
  }
}
