import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/models/library_list_state.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/providers/library_display_provider.dart';
import 'package:manhwamaniacs/features/library/providers/library_list_provider.dart';
import 'package:manhwamaniacs/features/library/providers/library_selection_provider.dart';
import 'package:manhwamaniacs/features/library/widgets/library/library_skeleton.dart';
import 'package:manhwamaniacs/features/library/widgets/library/library_toolbar.dart';
import 'package:manhwamaniacs/features/library/widgets/library/series_grid.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';

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

  void _showSeriesActions(FollowedSeries series) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetCtx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                context.space.xl2,
                0,
                context.space.xl2,
                context.space.sm,
              ),
              child: Text(
                series.title,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: context.text.h4,
              ),
            ),
            ListTile(
              leading: const Icon(Icons.open_in_new),
              title: const Text('Open'),
              onTap: () {
                Navigator.pop(sheetCtx);
                context.push(RoutePaths.seriesDetail(series.id));
              },
            ),
            ListTile(
              leading: Icon(
                series.isFavorite ? Icons.star : Icons.star_border,
                color: series.isFavorite ? context.colors.warning : null,
              ),
              title: Text(
                series.isFavorite ? 'Remove from favorites' : 'Add to favorites',
              ),
              onTap: () {
                Navigator.pop(sheetCtx);
                ref.read(libraryListProvider.notifier).toggleFavorite(series.id);
              },
            ),
            SizedBox(height: context.space.sm),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmBatchFavorite(Set<int> ids, {required bool favorite}) async {
    await ref
        .read(libraryListProvider.notifier)
        .batchSetFavorite(ids, favorite: favorite);
    if (mounted) {
      ref.read(librarySelectionProvider.notifier).exitSelectionMode();
    }
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(libraryQueryProvider);
    final listAsync = ref.watch(libraryListProvider);
    final coverScale = ref.watch(libraryCoverScaleProvider);
    final selection = ref.watch(librarySelectionProvider);
    final selectionController = ref.read(librarySelectionProvider.notifier);
    void onCoverScaleChanged(double value) =>
        ref.read(libraryCoverScaleProvider.notifier).setScale(value);

    return Scaffold(
      appBar: selection.active
          ? AppBar(
              title: Text('${selection.selectedIds.length} selected'),
              leading: IconButton(
                icon: const Icon(Icons.close),
                tooltip: 'Cancel selection',
                onPressed: selectionController.exitSelectionMode,
              ),
              actions: [
                IconButton(
                  icon: const Icon(Icons.select_all),
                  tooltip: 'Select all',
                  onPressed: () => selectionController.selectAll(
                    listAsync.valueOrNull?.items.map((s) => s.id) ?? const [],
                  ),
                ),
              ],
            )
          : AppBar(
              backgroundColor: Colors.transparent,
              leading: IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: () =>
                    context.canPop() ? context.pop() : context.go(Routes.library),
              ),
              actions: [
                IconButton(
                  icon: const Icon(Icons.checklist),
                  tooltip: 'Select series',
                  onPressed: selectionController.enterSelectionMode,
                ),
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
            padding: EdgeInsets.all(context.space.xl2),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const FadeIn(child: HeroHeading(text: 'Library')),
                SizedBox(height: context.space.xl2),
                LibraryToolbar(
                  query: query,
                  seriesCount: 0,
                  coverScale: coverScale,
                  onCoverScaleChanged: onCoverScaleChanged,
                  onSearchChanged: _onSearchChanged,
                  onSortChanged: (sort) =>
                      _updateQuery((q) => q.copyWith(sort: sort)),
                  onFilterChanged: (filter) =>
                      _updateQuery((q) => q.copyWith(filter: filter)),
                  onViewModeChanged: (viewMode) =>
                      _updateQuery((q) => q.copyWith(viewMode: viewMode)),
                ),
                SizedBox(height: context.space.xl2),
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
          scope: ref.watch(contentModeScopeProvider),
          scrollController: _scrollController,
          coverScale: coverScale,
          onCoverScaleChanged: onCoverScaleChanged,
          onRefresh: () => ref.read(libraryListProvider.notifier).refresh(),
          onSearchChanged: _onSearchChanged,
          onSortChanged: (sort) => _updateQuery((q) => q.copyWith(sort: sort)),
          onFilterChanged: (filter) =>
              _updateQuery((q) => q.copyWith(filter: filter)),
          onViewModeChanged: (viewMode) =>
              _updateQuery((q) => q.copyWith(viewMode: viewMode)),
          onSeriesTap: selection.active
              ? (series) => selectionController.toggle(series.id)
              : (series) => context.push(RoutePaths.seriesDetail(series.id)),
          onSeriesLongPress: selection.active ? null : _showSeriesActions,
          onToggleFavorite: (seriesId) =>
              ref.read(libraryListProvider.notifier).toggleFavorite(seriesId),
          selectionMode: selection.active,
          selectedIds: selection.selectedIds,
        ),
      ),
      bottomNavigationBar: selection.active && selection.selectedIds.isNotEmpty
          ? _SelectionActionBar(
              count: selection.selectedIds.length,
              onFavorite: () =>
                  _confirmBatchFavorite(selection.selectedIds, favorite: true),
              onUnfavorite: () =>
                  _confirmBatchFavorite(selection.selectedIds, favorite: false),
            )
          : null,
    );
  }
}

class _SelectionActionBar extends StatelessWidget {
  const _SelectionActionBar({
    required this.count,
    required this.onFavorite,
    required this.onUnfavorite,
  });

  final int count;
  final VoidCallback onFavorite;
  final VoidCallback onUnfavorite;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          context.space.lg,
          context.space.sm,
          context.space.lg,
          context.space.sm,
        ),
        child: Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: onFavorite,
                icon: Icon(Icons.star, size: 18, color: context.colors.warning),
                label: Text('Favorite ($count)'),
              ),
            ),
            SizedBox(width: context.space.md),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: onUnfavorite,
                icon: const Icon(Icons.star_border, size: 18),
                label: const Text('Unfavorite'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LibraryBody extends StatelessWidget {
  const _LibraryBody({
    required this.query,
    required this.state,
    required this.scope,
    required this.scrollController,
    required this.coverScale,
    required this.onCoverScaleChanged,
    required this.onRefresh,
    required this.onSearchChanged,
    required this.onSortChanged,
    required this.onFilterChanged,
    required this.onViewModeChanged,
    required this.onSeriesTap,
    required this.onSeriesLongPress,
    required this.onToggleFavorite,
    this.selectionMode = false,
    this.selectedIds = const {},
  });

  final LibraryQuery query;
  final LibraryListState state;

  /// The active Manga/Novels scope.
  ///
  /// Applied to the loaded rows rather than to the query, because `/library`
  /// has no `kind` parameter — follows carry a source id and the kind lives in
  /// the sources listing. The count line therefore reports the filtered rows
  /// whenever the filter actually removed any, rather than the server's total
  /// for a list it did not scope.
  final ContentModeScope scope;
  final ScrollController scrollController;
  final double coverScale;
  final ValueChanged<double> onCoverScaleChanged;
  final Future<void> Function() onRefresh;
  final ValueChanged<String> onSearchChanged;
  final ValueChanged<LibrarySort> onSortChanged;
  final ValueChanged<LibraryFilter> onFilterChanged;
  final ValueChanged<LibraryViewMode> onViewModeChanged;
  final ValueChanged<FollowedSeries> onSeriesTap;
  final ValueChanged<FollowedSeries>? onSeriesLongPress;
  final ValueChanged<int> onToggleFavorite;
  final bool selectionMode;
  final Set<int> selectedIds;

  @override
  Widget build(BuildContext context) {
    final visible = scope.filter(state.items, (series) => series.sourceId);
    return _LibraryScrollView(
      scrollController: scrollController,
      onRefresh: onRefresh,
      child: Padding(
        padding: EdgeInsets.all(context.space.xl2),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const FadeIn(child: HeroHeading(text: 'Library')),
            SizedBox(height: context.space.xl2),
            LibraryToolbar(
              query: query,
              seriesCount: visible.length == state.items.length
                  ? state.total
                  : visible.length,
              coverScale: coverScale,
              onCoverScaleChanged: onCoverScaleChanged,
              onSearchChanged: onSearchChanged,
              onSortChanged: onSortChanged,
              onFilterChanged: onFilterChanged,
              onViewModeChanged: onViewModeChanged,
            ),
            if (state.error != null) ...[
              SizedBox(height: context.space.lg),
              _InlineError(message: state.error!.userMessage),
            ],
            SizedBox(height: context.space.xl2),
            if (visible.isEmpty)
              LibraryEmptyPanel(emptyState: query.emptyState)
            else
              SeriesGrid(
                items: visible,
                viewMode: query.viewMode,
                coverScale: coverScale,
                onSeriesTap: onSeriesTap,
                onSeriesLongPress: onSeriesLongPress,
                onToggleFavorite: onToggleFavorite,
                selectionMode: selectionMode,
                selectedIds: selectedIds,
              ),
            if (state.isLoadingMore) ...[
              SizedBox(height: context.space.xl2),
              Center(
                child: Padding(
                  padding: EdgeInsets.all(context.space.lg),
                  child: const CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ],
            // Clear the floating nav bar and the home indicator under it. The
            // flat xl7 that used to be here only happened to be tall enough on
            // Android's ~24pt gesture inset; iOS's 34pt eats into it.
            SizedBox(
              height: context.space.xl7 + MediaQuery.paddingOf(context).bottom,
            ),
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
      color: context.colors.primary,
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
      padding: EdgeInsets.all(context.space.lg),
      decoration: BoxDecoration(
        color: context.colors.danger.withAlpha(26),
        borderRadius: BorderRadius.circular(context.radii.lg),
        border: Border.all(color: context.colors.danger.withAlpha(77)),
      ),
      child: Text(
        message,
        style: context.text.body.copyWith(color: context.colors.danger),
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
        padding: EdgeInsets.all(context.space.xl3),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, color: context.colors.danger, size: 48),
            SizedBox(height: context.space.lg),
            Text(
              'Could not load library',
              style: context.text.h3,
              textAlign: TextAlign.center,
            ),
            SizedBox(height: context.space.sm),
            Text(
              error.userMessage,
              style: context.text.body.copyWith(color: context.colors.muted),
              textAlign: TextAlign.center,
            ),
            SizedBox(height: context.space.xl2),
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