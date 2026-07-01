import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/app/theme/app_colors.dart';
import 'package:aistudio_mobile/app/theme/app_spacing.dart';
import 'package:aistudio_mobile/app/theme/app_typography.dart';
import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/features/sources/providers/sources_provider.dart';
import 'package:aistudio_mobile/shared/widgets/empty_state.dart';
import 'package:aistudio_mobile/shared/widgets/skeleton_box.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

class SourceBrowserScreen extends ConsumerStatefulWidget {
  const SourceBrowserScreen({super.key, required this.sourceId});

  final String sourceId;

  @override
  ConsumerState<SourceBrowserScreen> createState() => _SourceBrowserScreenState();
}

class _SourceBrowserScreenState extends ConsumerState<SourceBrowserScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _submitSearch() {
    ref.read(sourceBrowseQueryProvider(widget.sourceId).notifier).state = ref
        .read(sourceBrowseQueryProvider(widget.sourceId))
        .copyWith(search: _searchController.text.trim(), page: 1);
  }

  @override
  Widget build(BuildContext context) {
    final query = ref.watch(sourceBrowseQueryProvider(widget.sourceId));
    final browseAsync = ref.watch(sourceBrowseProvider(widget.sourceId));
    final modesAsync = ref.watch(sourceBrowseModesProvider(widget.sourceId));

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(Routes.sources),
        ),
        title: Text(widget.sourceId),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.xl2),
            child: Column(
              children: [
                TextField(
                  controller: _searchController,
                  decoration: InputDecoration(
                    hintText: 'Search series…',
                    prefixIcon: const Icon(Icons.search),
                    suffixIcon: IconButton(
                      icon: const Icon(Icons.arrow_forward),
                      onPressed: _submitSearch,
                    ),
                  ),
                  onSubmitted: (_) => _submitSearch(),
                ),
                const SizedBox(height: AppSpacing.md),
                modesAsync.when(
                  loading: () => const SizedBox.shrink(),
                  error: (_, __) => const SizedBox.shrink(),
                  data: (modes) {
                    if (modes.isEmpty || query.search.isNotEmpty) {
                      return const SizedBox.shrink();
                    }
                    return SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: [
                          for (final mode in modes)
                            Padding(
                              padding: const EdgeInsets.only(right: AppSpacing.sm),
                              child: ChoiceChip(
                                label: Text(mode.label),
                                selected: query.sort == mode.id,
                                onSelected: (_) {
                                  ref
                                      .read(sourceBrowseQueryProvider(widget.sourceId).notifier)
                                      .state = query.copyWith(sort: mode.id, page: 1);
                                },
                              ),
                            ),
                        ],
                      ),
                    );
                  },
                ),
              ],
            ),
          ),
          Expanded(
            child: browseAsync.when(
              loading: () => GridView.builder(
                padding: const EdgeInsets.all(AppSpacing.xl2),
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: AppSpacing.lg,
                  mainAxisSpacing: AppSpacing.lg,
                  childAspectRatio: 0.55,
                ),
                itemCount: 6,
                itemBuilder: (_, __) => const SkeletonBox(width: double.infinity, height: 220),
              ),
              error: (error, _) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      error is AppError ? error.userMessage : 'Failed to load source series.',
                      style: AppTypography.body.copyWith(color: AppColors.danger),
                    ),
                    const SizedBox(height: AppSpacing.lg),
                    FilledButton(
                      onPressed: () => ref.invalidate(sourceBrowseProvider(widget.sourceId)),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
              data: (page) {
                if (page.items.isEmpty) {
                  return EmptyState(
                    icon: Icons.search_off,
                    message: query.search.isEmpty
                        ? 'No series found'
                        : 'No series match your search',
                    subtitle: query.search.isEmpty
                        ? 'This source returned no browse results.'
                        : 'Try a different search term.',
                  );
                }

                return Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'Page ${page.page} · ${page.total} series',
                          style: AppTypography.caption.copyWith(color: AppColors.muted),
                        ),
                      ),
                    ),
                    Expanded(
                      child: GridView.builder(
                        padding: const EdgeInsets.all(AppSpacing.xl2),
                        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          crossAxisSpacing: AppSpacing.lg,
                          mainAxisSpacing: AppSpacing.lg,
                          childAspectRatio: 0.55,
                        ),
                        itemCount: page.items.length,
                        itemBuilder: (context, index) {
                          final series = page.items[index];
                          return _SourceSeriesCard(
                            series: series,
                            onTap: () => context.go(
                              RoutePaths.sourceSeriesDetail(widget.sourceId, series.id),
                            ),
                          );
                        },
                      ),
                    ),
                    if (page.hasNext || page.page > 1)
                      Padding(
                        padding: const EdgeInsets.all(AppSpacing.xl2),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            OutlinedButton(
                              onPressed: page.page <= 1
                                  ? null
                                  : () {
                                      ref
                                          .read(
                                            sourceBrowseQueryProvider(widget.sourceId).notifier,
                                          )
                                          .state = query.copyWith(page: query.page - 1);
                                    },
                              child: const Text('Previous'),
                            ),
                            OutlinedButton(
                              onPressed: !page.hasNext
                                  ? null
                                  : () {
                                      ref
                                          .read(
                                            sourceBrowseQueryProvider(widget.sourceId).notifier,
                                          )
                                          .state = query.copyWith(page: query.page + 1);
                                    },
                              child: const Text('Next'),
                            ),
                          ],
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SourceSeriesCard extends StatelessWidget {
  const _SourceSeriesCard({required this.series, required this.onTap});

  final SourceSeriesSummary series;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Ink(
        decoration: BoxDecoration(
          color: AppColors.panel,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.border.withAlpha(80)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                child: Image.network(
                  series.coverUrl,
                  fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const ColoredBox(color: AppColors.panel),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    series.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.labelLg,
                  ),
                  Text(
                    '${series.chapterCount} chapters',
                    style: AppTypography.caption.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
