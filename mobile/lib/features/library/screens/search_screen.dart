import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/responsive.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/providers/library_list_provider.dart';
import 'package:manhwamaniacs/features/library/utils/recent_searches.dart';
import 'package:manhwamaniacs/features/library/widgets/library/library_skeleton.dart';
import 'package:manhwamaniacs/features/library/widgets/search/global_search_result_card.dart';
import 'package:manhwamaniacs/features/library/widgets/search/search_result_card.dart';
import 'package:manhwamaniacs/features/library/widgets/search/search_suggestions.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';

class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _scrollController = ScrollController();
  final _searchController = TextEditingController();
  Timer? _searchDebounce;
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
    final profileId = ref.read(activeProfileProvider)?.id;
    setState(
      () => _recentSearches = readRecentSearches(prefs, profileId: profileId),
    );
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.pixels >= position.maxScrollExtent - 320) {
      ref.read(searchListProvider.notifier).loadMore();
    }
  }

  /// Debounce keystrokes so we only issue a federated search once typing
  /// settles — this is the first line of stale-response defence.
  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () {
      ref.read(searchQueryProvider.notifier).state = value.trim();
    });
  }

  void _applySuggestion(String value) {
    _searchDebounce?.cancel();
    _searchController.text = value;
    ref.read(searchQueryProvider.notifier).state = value.trim();
  }

  Future<void> _persistRecentSearch(String trimmedQuery) async {
    if (trimmedQuery.length < 2 || _lastPersistedQuery == trimmedQuery) return;
    _lastPersistedQuery = trimmedQuery;
    final prefs = ref.read(sharedPrefsProvider);
    final profileId = ref.read(activeProfileProvider)?.id;
    await writeRecentSearch(prefs, trimmedQuery, profileId: profileId);
    if (mounted) {
      setState(
        () => _recentSearches = readRecentSearches(prefs, profileId: profileId),
      );
    }
  }

  void _openItem(GlobalSearchItem item) {
    if (item.isLocal) {
      final id = int.tryParse(item.seriesId);
      if (id != null) context.push(RoutePaths.seriesDetail(id));
      return;
    }
    final source = item.source;
    if (source != null && source.isNotEmpty) {
      context.push(RoutePaths.sourceSeriesDetail(source, item.seriesId));
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(searchQueryProvider).trim();
    final viewMode = ref.watch(searchViewModeProvider);
    final listAsync = ref.watch(searchListProvider);
    final hasQuery = query.isNotEmpty;

    ref.listen<AsyncValue<GlobalSearchResult>>(searchListProvider,
        (previous, next) {
      next.whenData((state) {
        if (hasQuery && !next.isLoading && state.items.isNotEmpty) {
          _persistRecentSearch(query);
        }
      });
    });

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: listAsync.when(
        skipLoadingOnReload: true,
        loading: () => _SearchScrollView(
          scrollController: _scrollController,
          onRefresh: () => ref.read(searchListProvider.notifier).refresh(),
          slivers: _contentSlivers(
            hasQuery: hasQuery,
            viewMode: viewMode,
            isLoading: true,
            state: null,
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
          slivers: _contentSlivers(
            hasQuery: hasQuery,
            viewMode: viewMode,
            isLoading: false,
            state: state,
          ),
        ),
      ),
    );
  }

  /// Builds the search screen as lazily-evaluated slivers so paginated results
  /// stay virtualized: the header is one adapter sliver and the results are a
  /// SliverList/SliverGrid.builder, so only on-screen cards (and their
  /// auth-gated cover images) are materialized as the user scrolls.
  List<Widget> _contentSlivers({
    required bool hasQuery,
    required LibraryViewMode viewMode,
    required bool isLoading,
    required GlobalSearchResult? state,
  }) {
    const horizontalPadding = EdgeInsets.symmetric(horizontal: AppSpacing.xl2);
    final showResults =
        hasQuery && !isLoading && state != null && !state.isEmpty;

    final slivers = <Widget>[
      SliverPadding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl2,
          AppSpacing.xl2,
          AppSpacing.xl2,
          0,
        ),
        sliver: SliverToBoxAdapter(
          child: _SearchHeader(
            hasQuery: hasQuery,
            isLoading: isLoading,
            viewMode: viewMode,
            state: state,
            recentSearches: _recentSearches,
            searchController: _searchController,
            onSearchChanged: _onSearchChanged,
            onSelectSuggestion: _applySuggestion,
            onViewModeChanged: (mode) =>
                ref.read(searchViewModeProvider.notifier).state = mode,
          ),
        ),
      ),
    ];

    if (showResults) {
      final items = state.items;
      if (viewMode == LibraryViewMode.grid) {
        final columns = context.seriesGridColumns.clamp(2, 6);
        slivers.add(
          SliverPadding(
            padding: horizontalPadding,
            sliver: SliverGrid.builder(
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: columns,
                crossAxisSpacing: AppSpacing.md,
                mainAxisSpacing: AppSpacing.xl,
                childAspectRatio: 0.56,
              ),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index];
                return ScrollReveal(
                  index: index,
                  child: GlobalSearchResultGridCard(
                    item: item,
                    onTap: () => _openItem(item),
                  ),
                );
              },
            ),
          ),
        );
      } else {
        slivers.add(
          SliverPadding(
            padding: horizontalPadding,
            sliver: SliverList.builder(
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index];
                return Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.md),
                  child: ScrollReveal(
                    index: index,
                    child: GlobalSearchResultCard(
                      item: item,
                      onTap: () => _openItem(item),
                    ),
                  ),
                );
              },
            ),
          ),
        );
      }
    }

    slivers.add(
      SliverPadding(
        padding: horizontalPadding,
        sliver: SliverToBoxAdapter(
          child: Column(
            children: [
              if (showResults && state.isLoadingMore) ...[
                const SizedBox(height: AppSpacing.xl2),
                const Center(
                  child: Padding(
                    padding: EdgeInsets.all(AppSpacing.lg),
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      color: AppColors.primary,
                    ),
                  ),
                ),
              ],
              const SizedBox(height: AppSpacing.xl3),
            ],
          ),
        ),
      ),
    );

    return slivers;
  }
}

/// Non-result header: hero heading, search field, the status/progress line and
/// view toggle, and the pre-results states (suggestions, loading skeleton, and
/// the empty "No results found" panel). The result cards are rendered as
/// separate virtualized slivers by the parent.
class _SearchHeader extends StatelessWidget {
  const _SearchHeader({
    required this.hasQuery,
    required this.isLoading,
    required this.viewMode,
    required this.recentSearches,
    required this.searchController,
    required this.onSearchChanged,
    required this.onSelectSuggestion,
    required this.onViewModeChanged,
    this.state,
  });

  final bool hasQuery;
  final bool isLoading;
  final LibraryViewMode viewMode;
  final GlobalSearchResult? state;
  final List<String> recentSearches;
  final TextEditingController searchController;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<String> onSelectSuggestion;
  final ValueChanged<LibraryViewMode> onViewModeChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const FadeIn(
          child: Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.xl2),
            child: Align(
              alignment: Alignment.centerLeft,
              child: HeroHeading(text: 'Search', fontSize: 40),
            ),
          ),
        ),
        TextField(
          controller: searchController,
          onChanged: onSearchChanged,
          textInputAction: TextInputAction.search,
          decoration: InputDecoration(
            prefixIcon: const Icon(Icons.search, color: AppColors.muted),
            hintText: 'Search manga, manhwa, webtoons…',
            filled: true,
            fillColor: AppColors.fg.withAlpha(8),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: AppColors.border.withAlpha(128)),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: AppColors.border.withAlpha(128)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.xl),
              borderSide: BorderSide(color: AppColors.primary.withAlpha(77)),
            ),
            contentPadding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.xl2,
              vertical: AppSpacing.lg,
            ),
          ),
        ),
        if (!hasQuery) ...[
          const SizedBox(height: AppSpacing.xl2),
          SearchSuggestionsPanel(
            recentSearches: recentSearches,
            onSelect: onSelectSuggestion,
            filtersOpen: false,
            onToggleFilters: () {},
          ),
        ],
        if (hasQuery) ...[
          const SizedBox(height: AppSpacing.xl2),
          Row(
            children: [
              Expanded(
                child: _StatusLine(isLoading: isLoading, state: state),
              ),
              _ViewModeToggle(
                viewMode: viewMode,
                onChanged: onViewModeChanged,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          if (isLoading)
            SearchResultsSkeleton(viewMode: viewMode)
          else if (state != null && state!.isEmpty)
            const LibraryEmptyPanel(emptyState: LibraryEmptyState.search),
        ],
      ],
    );
  }
}

/// The search status/progress line — never an endless spinner. While a request
/// is in flight it reads "Searching sources…"; once resolved it reports the
/// result count and how many sources were queried, plus a subtle unavailable
/// note when some sources failed.
class _StatusLine extends StatelessWidget {
  const _StatusLine({required this.isLoading, required this.state});

  final bool isLoading;
  final GlobalSearchResult? state;

  @override
  Widget build(BuildContext context) {
    if (isLoading || state == null) {
      return Text(
        'Searching sources…',
        style: AppTypography.body.copyWith(color: AppColors.muted),
      );
    }

    final count = state!.items.length;
    final queried = state!.sourcesQueried;
    final failed = state!.sourcesFailed;

    final buffer = StringBuffer()
      ..write('$count ${count == 1 ? 'result' : 'results'} found');
    if (queried > 0) {
      buffer.write(' · $queried ${queried == 1 ? 'source' : 'sources'}');
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          buffer.toString(),
          style: AppTypography.body.copyWith(color: AppColors.muted),
        ),
        if (failed > 0) ...[
          const SizedBox(height: 2),
          Text(
            'Some sources unavailable',
            style: AppTypography.caption.copyWith(
              color: AppColors.warning.withAlpha(204),
            ),
          ),
        ],
      ],
    );
  }
}

class _ViewModeToggle extends StatelessWidget {
  const _ViewModeToggle({required this.viewMode, required this.onChanged});

  final LibraryViewMode viewMode;
  final ValueChanged<LibraryViewMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.fg.withAlpha(13),
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.border.withAlpha(128)),
      ),
      padding: const EdgeInsets.all(2),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _ModeButton(
            icon: Icons.grid_view,
            selected: viewMode == LibraryViewMode.grid,
            onTap: () => onChanged(LibraryViewMode.grid),
          ),
          _ModeButton(
            icon: Icons.view_list,
            selected: viewMode == LibraryViewMode.list,
            onTap: () => onChanged(LibraryViewMode.list),
          ),
        ],
      ),
    );
  }
}

class _ModeButton extends StatelessWidget {
  const _ModeButton({
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.primary : Colors.transparent,
      borderRadius: BorderRadius.circular(AppRadius.sm),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.sm),
        child: SizedBox(
          width: 32,
          height: 32,
          child: Icon(
            icon,
            size: 18,
            color: selected ? AppColors.primaryFg : AppColors.muted,
          ),
        ),
      ),
    );
  }
}

class _SearchScrollView extends StatelessWidget {
  const _SearchScrollView({
    required this.scrollController,
    required this.onRefresh,
    required this.slivers,
  });

  final ScrollController scrollController;
  final Future<void> Function() onRefresh;
  final List<Widget> slivers;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: onRefresh,
      color: AppColors.primary,
      child: CustomScrollView(
        controller: scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: slivers,
      ),
    );
  }
}

class _SearchError extends StatelessWidget {
  const _SearchError({required this.error, required this.onRetry});

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
            PrimaryPillButton(
              label: 'Try Again',
              icon: Icons.refresh,
              onPressed: onRetry,
            ),
          ],
        ),
      ),
    );
  }
}
