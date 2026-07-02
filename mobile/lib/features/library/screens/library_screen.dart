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
import 'package:aistudio_mobile/features/library/widgets/library/library_skeleton.dart';
import 'package:aistudio_mobile/features/library/widgets/library/library_toolbar.dart';
import 'package:aistudio_mobile/features/library/widgets/library/series_grid.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class LibraryScreen extends ConsumerStatefulWidget {
  const LibraryScreen({super.key});

  @override
  ConsumerState<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends ConsumerState<LibraryScreen> {
  final _scrollController = ScrollController();
  Timer? _searchDebounce;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _scrollController
      ..removeListener(_onScroll)
      ..dispose();
    super.dispose();
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.pixels >= position.maxScrollExtent - 320) {
      ref.read(libraryListProvider.notifier).loadMore();
    }
  }

  void _updateQuery(LibraryQuery Function(LibraryQuery current) update) {
    ref.read(libraryQueryProvider.notifier).patchQuery(update);
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 300), () {
      _updateQuery((query) => query.copyWith(search: value));
    });
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(libraryQueryProvider);
    final listAsync = ref.watch(libraryListProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Browse Library'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.canPop() ? context.pop() : context.go(Routes.library),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.bookmark_outline),
            tooltip: 'Bookmarks',
            onPressed: () => context.push(Routes.bookmarks),
          ),
        ],
      ),
      body: listAsync.when(
        loading: () => _LibraryScrollView(
          scrollController: _scrollController,
          onRefresh: () => ref.read(libraryListProvider.notifier).refresh(),
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LibraryToolbar(
                  query: query,
                  seriesCount: 0,
                  onSearchChanged: _onSearchChanged,
                  onSortChanged: (sort) =>
                      _updateQuery((q) => q.copyWith(sort: sort)),
                  onFilterChanged: (filter) =>
                      _updateQuery((q) => q.copyWith(filter: filter)),
                  onViewModeChanged: (viewMode) =>
                      _updateQuery((q) => q.copyWith(viewMode: viewMode)),
                ),
                const SizedBox(height: AppSpacing.xl2),
                LibrarySkeleton(viewMode: query.viewMode),
              ],
            ),
          ),
        ),
        error: (error, _) => _LibraryError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.read(libraryListProvider.notifier).refresh(),
        ),
        data: (state) => _LibraryBody(
          query: query,
          state: state,
          scrollController: _scrollController,
          onRefresh: () => ref.read(libraryListProvider.notifier).refresh(),
          onSearchChanged: _onSearchChanged,
          onSortChanged: (sort) => _updateQuery((q) => q.copyWith(sort: sort)),
          onFilterChanged: (filter) =>
              _updateQuery((q) => q.copyWith(filter: filter)),
          onViewModeChanged: (viewMode) =>
              _updateQuery((q) => q.copyWith(viewMode: viewMode)),
          onSeriesTap: (series) => context.push(RoutePaths.seriesDetail(series.id)),
          onToggleFavorite: (seriesId) =>
              ref.read(libraryListProvider.notifier).toggleFavorite(seriesId),
        ),
      ),
    );
  }
}

class _LibraryBody extends StatelessWidget {
  const _LibraryBody({
    required this.query,
    required this.state,
    required this.scrollController,
    required this.onRefresh,
    required this.onSearchChanged,
    required this.onSortChanged,
    required this.onFilterChanged,
    required this.onViewModeChanged,
    required this.onSeriesTap,
    required this.onToggleFavorite,
  });

  final LibraryQuery query;
  final LibraryListState state;
  final ScrollController scrollController;
  final Future<void> Function() onRefresh;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;
  final ValueChanged<SeriesSummary> onSeriesTap;
  final ValueChanged<int> onToggleFavorite;

  @override
  Widget build(BuildContext context) {
    return _LibraryScrollView(
      scrollController: scrollController,
      onRefresh: onRefresh,
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LibraryToolbar(
              query: query,
              seriesCount: state.total,
              onSearchChanged: onSearchChanged,
              onSortChanged: onSortChanged,
          onFilterChanged: onFilterChanged,
          onViewModeChanged: onViewModeChanged,
            ),
            if (state.error != null) ...[
              const SizedBox(height: AppSpacing.lg),
              _InlineError(message: state.error!.userMessage),
            ],
            const SizedBox(height: AppSpacing.xl2),
            if (state.isEmpty)
              LibraryEmptyPanel(emptyState: query.emptyState)
            else
              SeriesGrid(
                items: state.items,
                viewMode: query.viewMode,
                onSeriesTap: onSeriesTap,
                onToggleFavorite: onToggleFavorite,
              ),
            if (state.isLoadingMore) ...[
              const SizedBox(height: AppSpacing.xl2),
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(AppSpacing.lg),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ],
            const SizedBox(height: AppSpacing.xl3),
          ],
        ),
      ),
    );
  }
}

class _LibraryScrollView extends StatelessWidget {
  const _LibraryScrollView({
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

class _LibraryError extends StatelessWidget {
  const _LibraryError({
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
              'Could not load library',
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
