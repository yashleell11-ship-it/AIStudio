import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_presets.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode.dart';
import 'package:manhwamaniacs/features/content_mode/content_mode_controller.dart';
import 'package:manhwamaniacs/features/novels/widgets/novel_shelf.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/source_branding.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/pressable.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';
import 'package:manhwamaniacs/shared/widgets/series_cover_image.dart';

class SourceBrowserScreen extends ConsumerStatefulWidget {
  const SourceBrowserScreen({super.key, required this.sourceId});

  final String sourceId;

  @override
  ConsumerState<SourceBrowserScreen> createState() =>
      _SourceBrowserScreenState();
}

class _SourceBrowserScreenState extends ConsumerState<SourceBrowserScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();
  bool _showBackToTop = false;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    final show = _scrollController.offset > 400;
    if (show != _showBackToTop) {
      setState(() => _showBackToTop = show);
    }
    if (!_scrollController.hasClients) return;
    final position = _scrollController.position;
    if (position.pixels >= position.maxScrollExtent - 600) {
      ref.read(sourceBrowseProvider(widget.sourceId).notifier).loadMore();
    }
  }

  void _submitSearch() {
    final q = _searchController.text.trim();
    ref.read(sourceBrowseQueryProvider(widget.sourceId).notifier).state =
        ref.read(sourceBrowseQueryProvider(widget.sourceId)).copyWith(search: q);
  }

  void _clearSearch() {
    _searchController.clear();
    ref.read(sourceBrowseQueryProvider(widget.sourceId).notifier).state =
        ref.read(sourceBrowseQueryProvider(widget.sourceId)).copyWith(search: '');
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(sourceBrowseQueryProvider(widget.sourceId));
    final browseAsync = ref.watch(sourceBrowseProvider(widget.sourceId));
    final modesAsync = ref.watch(sourceBrowseModesProvider(widget.sourceId));
    final source = ref
        .watch(sourcesListProvider)
        .valueOrNull
        ?.firstWhereOrNull((s) => s.id == widget.sourceId);
    final sourceName = source?.name ?? prettifySourceId(widget.sourceId);
    // A property of the SOURCE, not of the reader's current mode: browsing a
    // novel archive reached from anywhere must render a shelf.
    final isNovelSource =
        ref.watch(contentModeScopeProvider).modeOf(widget.sourceId) ==
            ContentMode.novel;

    // Subtle confirmation the moment the catalog resolves (success or error),
    // honouring the user's interaction-feedback preference via hapticsProvider.
    ref.listen<AsyncValue<SourceBrowseState>>(
      sourceBrowseProvider(widget.sourceId),
      (previous, next) {
        if (previous != null && previous.isLoading && !next.isLoading) {
          ref.read(hapticsProvider).light();
        }
      },
    );

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(Routes.sources),
        ),
        title: Row(
          children: [
            SourceLogo(
              id: widget.sourceId,
              name: sourceName,
              iconUrl: source?.iconUrl,
              size: 28,
            ),
            SizedBox(width: context.space.sm),
            Expanded(
              child: Text(
                sourceName,
                style: context.text.h4.copyWith(color: context.colors.primary),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        titleSpacing: 0,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              context.space.lg,
              0,
              context.space.lg,
              context.space.sm,
            ),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: 'Search series…',
                hintStyle: context.text.body.copyWith(color: context.colors.muted),
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: query.search.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.close, size: 18),
                        onPressed: _clearSearch,
                      )
                    : IconButton(
                        icon: const Icon(Icons.arrow_forward, size: 18),
                        onPressed: _submitSearch,
                      ),
                isDense: true,
                contentPadding: const EdgeInsets.symmetric(vertical: 10),
              ),
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _submitSearch(),
            ),
          ),
        ),
      ),
      body: Stack(
        children: [
          Column(
            children: [
              // Sort/mode chips
              modesAsync.when(
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
                data: (modes) {
                  if (modes.isEmpty || query.search.isNotEmpty) {
                    return const SizedBox.shrink();
                  }
                  return SizedBox(
                    height: 44,
                    child: ListView.separated(
                      scrollDirection: Axis.horizontal,
                      padding: EdgeInsets.symmetric(
                        horizontal: context.space.lg,
                        vertical: context.space.sm,
                      ),
                      itemCount: modes.length,
                      separatorBuilder: (_, __) =>
                          SizedBox(width: context.space.xs),
                      itemBuilder: (context, i) {
                        final mode = modes[i];
                        final selected = query.sort == mode.id;
                        return ChoiceChip(
                          label: Text(mode.label),
                          selected: selected,
                          visualDensity: VisualDensity.compact,
                          onSelected: (_) {
                            ref
                                .read(
                                  sourceBrowseQueryProvider(
                                    widget.sourceId,
                                  ).notifier,
                                )
                                .state =
                                query.copyWith(sort: mode.id);
                          },
                        );
                      },
                    ),
                  );
                },
              ),
              Expanded(
                child: AnimatedSwitcher(
                  duration: MediaQuery.disableAnimationsOf(context)
                      ? Duration.zero
                      : const Duration(milliseconds: 450),
                  switchInCurve: Curves.easeOut,
                  switchOutCurve: Curves.easeIn,
                  child: browseAsync.when(
                    skipLoadingOnReload: true,
                    loading: () => KeyedSubtree(
                      key: const ValueKey('source-browse-loading'),
                      child: _SourceOpeningState(
                        sourceId: widget.sourceId,
                        sourceName: sourceName,
                        iconUrl: source?.iconUrl,
                      ),
                    ),
                    error: (error, _) => KeyedSubtree(
                      key: const ValueKey('source-browse-error'),
                      child: _buildError(error),
                    ),
                    data: (state) {
                      if (state.isEmpty) {
                        return KeyedSubtree(
                          key: const ValueKey('source-browse-empty'),
                          child: EmptyState(
                            icon: Icons.search_off,
                            message: query.search.isEmpty
                                ? 'No series found'
                                : 'No results for "${query.search}"',
                            subtitle: query.search.isEmpty
                                ? 'This source returned no browse results.'
                                : 'Try a different search term.',
                          ),
                        );
                      }

                      return RefreshIndicator(
                        key: const ValueKey('source-browse-data'),
                        color: context.colors.primary,
                        onRefresh: () => ref
                            .read(sourceBrowseProvider(widget.sourceId).notifier)
                            .refresh(),
                        child: CustomScrollView(
                          controller: _scrollController,
                          slivers: [
                          // Result count header
                          SliverPadding(
                            padding: EdgeInsets.fromLTRB(
                              context.space.lg,
                              context.space.sm,
                              context.space.lg,
                              context.space.sm,
                            ),
                            sliver: SliverToBoxAdapter(
                              child: Text(
                                isNovelSource
                                    ? '${state.total} '
                                        '${state.total == 1 ? 'book' : 'books'}'
                                    : '${state.total} series',
                                style: context.text.caption.copyWith(color: context.colors.muted),
                              ),
                            ),
                          ),
                          // A shelf of rows for prose, a poster grid for
                          // pages. Novel covers are usually an aggregator's
                          // generated placeholder, so three columns of them
                          // would be three columns of interchangeable
                          // rectangles — see [NovelShelf].
                          if (isNovelSource)
                            NovelShelf(
                              itemCount: state.items.length,
                              bookAt: (index) {
                                final series = state.items[index];
                                return ShelfBook(
                                  title: series.title,
                                  author: series.author,
                                  description: series.description,
                                  chapterCount: series.chapterCount,
                                  status: series.status,
                                  coverUrl: series.coverUrl.isEmpty
                                      ? null
                                      : series.coverUrl,
                                  onTap: () => context.go(
                                    RoutePaths.sourceSeriesDetail(
                                      widget.sourceId,
                                      series.id,
                                    ),
                                  ),
                                );
                              },
                            )
                          else
                          SliverPadding(
                            padding: EdgeInsets.symmetric(
                              horizontal: context.space.sm,
                            ),
                            sliver: SliverGrid.builder(
                              gridDelegate:
                                  SliverGridDelegateWithFixedCrossAxisCount(
                                crossAxisCount: 3,
                                crossAxisSpacing: context.space.xs,
                                mainAxisSpacing: context.space.xs,
                                childAspectRatio: 0.56,
                              ),
                              itemCount: state.items.length,
                              itemBuilder: (context, index) {
                                final series = state.items[index];
                                return ScrollReveal(
                                  index: index,
                                  child: _DenseSeriesCard(
                                    series: series,
                                    onTap: () => context.go(
                                      RoutePaths.sourceSeriesDetail(
                                        widget.sourceId,
                                        series.id,
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),
                          if (state.isLoadingMore)
                            SliverPadding(
                              padding: EdgeInsets.symmetric(vertical: context.space.xl2),
                              sliver: const SliverToBoxAdapter(
                                child: Center(
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                ),
                              ),
                            ),
                          // Bottom padding for the floating back-to-top button
                          const SliverPadding(
                            padding: EdgeInsets.only(bottom: 80),
                          ),
                        ],
                      ),
                    );
                  },
                ),
                ),
              ),
            ],
          ),

          // Floating back-to-top button (always on top of grid)
          if (_showBackToTop)
            Positioned(
              bottom: MediaQuery.paddingOf(context).bottom + context.space.xl7 + context.space.sm,
              right: context.space.lg,
              child: _NavPill(
                icon: Icons.keyboard_arrow_up,
                label: 'Top',
                outlined: true,
                onTap: () => _scrollController.animateTo(
                  0,
                  duration: const Duration(milliseconds: 400),
                  curve: Curves.easeOut,
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildError(Object error) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            error is AppError
                ? error.userMessage
                : 'Failed to load source series.',
            style: context.text.body.copyWith(color: context.colors.danger),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: context.space.lg),
          FilledButton(
            onPressed: () =>
                ref.invalidate(sourceBrowseProvider(widget.sourceId)),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }
}

// ── Floating page navigation controls ─────────────────────────────────────────

class _NavPill extends StatelessWidget {
  const _NavPill({
    required this.icon,
    required this.label,
    required this.onTap,
    this.outlined = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool outlined;

  @override
  Widget build(BuildContext context) {
    final content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: context.colors.primaryFg),
        SizedBox(width: context.space.xs),
        Text(
          label,
          style: context.text.labelLg.copyWith(color: context.colors.primaryFg),
        ),
      ],
    );

    if (outlined) {
      return Material(
        color: context.colors.panel.withAlpha(230),
        borderRadius: BorderRadius.circular(context.radii.full),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(context.radii.full),
          child: Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.space.md,
              vertical: context.space.sm,
            ),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(context.radii.full),
              border: Border.all(color: context.colors.border),
            ),
            child: content,
          ),
        ),
      );
    }

    return FilledButton(
      onPressed: onTap,
      style: FilledButton.styleFrom(
        padding: EdgeInsets.symmetric(
          horizontal: context.space.md,
          vertical: context.space.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(context.radii.full),
        ),
      ),
      child: content,
    );
  }
}

// ── Catalog opening state ─────────────────────────────────────────────────────

/// Shown while a source catalog is being fetched: the source logo, an
/// "Opening {name}…" line, and a warm amber spinner. Deliberately minimal — the
/// app bar already names the source, so this never duplicates the heading.
class _SourceOpeningState extends StatelessWidget {
  const _SourceOpeningState({
    required this.sourceId,
    required this.sourceName,
    this.iconUrl,
  });

  final String sourceId;
  final String sourceName;
  final String? iconUrl;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(context.space.xl2),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SourceLogo(
              id: sourceId,
              name: sourceName,
              iconUrl: iconUrl,
              size: 72,
            ),
            SizedBox(height: context.space.xl),
            Text(
              'Opening $sourceName…',
              textAlign: TextAlign.center,
              style: context.text.h4,
            ),
            SizedBox(height: context.space.xl),
            SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(
                strokeWidth: 2.5,
                valueColor: AlwaysStoppedAnimation<Color>(context.colors.primary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Dense cover-focused card ──────────────────────────────────────────────────

class _DenseSeriesCard extends StatelessWidget {
  const _DenseSeriesCard({required this.series, required this.onTap});

  final SourceSeriesSummary series;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Pressable(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(context.radii.md),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: context.colors.surface,
            borderRadius: BorderRadius.circular(context.radii.md),
            border: Border.all(color: context.colors.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                flex: 6,
                child: SeriesCoverImage(
                  url: series.coverUrl,
                  borderRadius: 0,
                ),
              ),
              Expanded(
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: context.space.xs,
                    vertical: context.space.xxs,
                  ),
                  child: Text(
                    series.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: context.text.caption.copyWith(
                      color: context.colors.fg,
                      fontSize: 10,
                      height: 1.2,
                    ),
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
