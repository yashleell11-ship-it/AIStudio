import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_pin.dart';
import 'package:manhwamaniacs/features/sources/providers/source_pins_provider.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/widgets/filter_pill.dart';
import 'package:manhwamaniacs/features/sources/widgets/source_row_card.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/section_header.dart';

/// The Sources screen: a searchable row list with a Pinned section.
///
/// This deliberately breaks the "sources grid = logo+name only" rule in
/// `docs/DESIGN_SYSTEM.md` (updated to match). At ~50 connectors the grid had
/// become a wall of 16px favicons upscaled to 60 with no way to reach a
/// specific one; a filterable list with a pinned section is the shape that
/// actually scales.
class SourcesListScreen extends ConsumerStatefulWidget {
  const SourcesListScreen({super.key});

  @override
  ConsumerState<SourcesListScreen> createState() => _SourcesListScreenState();
}

class _SourcesListScreenState extends ConsumerState<SourcesListScreen> {
  final _filterController = TextEditingController();

  @override
  void initState() {
    super.initState();
    // The filter lives in a provider, so restore it when the tab is re-entered.
    _filterController.text = ref.read(sourcesFilterQueryProvider);
  }

  @override
  void dispose() {
    _filterController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    ref.invalidate(sourcesListProvider);
    final pins = ref.read(sourcePinsProvider.notifier).refresh();
    await ref.read(sourcesListProvider.future);
    await pins;
  }

  @override
  Widget build(BuildContext context) {
    final sourcesAsync = ref.watch(sourcesListProvider);
    final query = ref.watch(sourcesFilterQueryProvider).trim().toLowerCase();
    final filter = ref.watch(sourcesFilterProvider);
    final pins = ref.watch(sourcePinsProvider).valueOrNull?.pins ?? const [];

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: RefreshIndicator(
          color: context.colors.primary,
          onRefresh: _refresh,
          child: CustomScrollView(
            physics: const AlwaysScrollableScrollPhysics(),
            slivers: [
              const SliverPadding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.lg,
                  AppSpacing.lg,
                  AppSpacing.lg,
                  AppSpacing.md,
                ),
                sliver: SliverToBoxAdapter(
                  child: HeroHeading(text: 'Sources', fontSize: 40),
                ),
              ),
              SliverPersistentHeader(
                pinned: true,
                delegate: _SourcesFilterBar(
                  controller: _filterController,
                  query: query,
                  filter: filter,
                  pinnedCount: pins.length,
                  onQueryChanged: (value) =>
                      ref.read(sourcesFilterQueryProvider.notifier).state = value,
                  onFilterChanged: (value) =>
                      ref.read(sourcesFilterProvider.notifier).state = value,
                ),
              ),
              ...sourcesAsync.when(
                loading: () => const [_SourcesSkeletonSliver()],
                error: (error, _) => [
                  _SourcesErrorSliver(
                    message: error is AppError
                        ? error.userMessage
                        : 'Failed to load sources.',
                    onRetry: () => ref.invalidate(sourcesListProvider),
                  ),
                ],
                data: (sources) => _sectionSlivers(
                  sources: sources,
                  pins: pins,
                  query: query,
                  filter: filter,
                ),
              ),
              SliverToBoxAdapter(
                child: SizedBox(
                  height: AppSpacing.xl7 + MediaQuery.paddingOf(context).bottom,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _sectionSlivers({
    required List<SourceSummary> sources,
    required List<SourcePin> pins,
    required String query,
    required SourcesFilter filter,
  }) {
    if (sources.isEmpty) {
      return const [
        SliverFillRemaining(
          hasScrollBody: false,
          child: EmptyState(
            icon: Icons.public_off,
            message: 'No sources installed',
          ),
        ),
      ];
    }

    final byId = {for (final source in sources) source.id: source};
    final pinnedIds = {for (final pin in pins) pin.sourceId};

    // Pinned rows follow the server's pin order. A pin whose connector no
    // longer resolves is rendered from the pin's own metadata so it can still
    // be cleared, rather than disappearing from the ordering.
    final pinned = <({SourceSummary source, bool unavailable})>[
      for (final pin in pins)
        if (byId[pin.sourceId] case final source?)
          (source: source, unavailable: false)
        else
          (source: _placeholderSource(pin), unavailable: true),
    ].where((row) => _matches(row.source, query, filter)).toList();

    // No re-sort here: /sources is already ordered case-insensitively by the
    // backend, and re-sorting with String.compareTo put every lowercase id
    // after every uppercase one.
    //
    // Everything in this list is by definition unpinned, so the Pinned scope
    // empties it outright — filtering it through [_matches] would leave the
    // chip inert and still render all ~50 rows under "All sources".
    final rest = filter == SourcesFilter.pinned
        ? const <SourceSummary>[]
        : [
            for (final source in sources)
              if (!pinnedIds.contains(source.id) &&
                  _matches(source, query, filter))
                source,
          ];

    if (pinned.isEmpty && rest.isEmpty) {
      return [
        SliverFillRemaining(
          hasScrollBody: false,
          child: EmptyState(
            icon: Icons.search_off,
            message: filter == SourcesFilter.pinned
                ? 'No pinned sources'
                : 'No sources match',
            subtitle: filter == SourcesFilter.pinned
                ? 'Tap the pin on any source to keep it at the top.'
                : 'Try a different name.',
          ),
        ),
      ];
    }

    final slivers = <Widget>[];
    var revealIndex = 0;

    if (pinned.isNotEmpty) {
      slivers
        ..add(const _SectionHeaderSliver(icon: Icons.push_pin, title: 'Pinned'))
        ..add(
          _rowsSliver(
            count: pinned.length,
            revealOffset: revealIndex,
            builder: (index) => SourceRowCard(
              source: pinned[index].source,
              unavailable: pinned[index].unavailable,
              onTap: () => _open(pinned[index].source),
            ),
          ),
        );
      revealIndex += pinned.length;
    }

    if (rest.isNotEmpty) {
      slivers
        ..add(
          _SectionHeaderSliver(
            icon: Icons.travel_explore,
            title: pinned.isEmpty ? 'Sources' : 'All sources',
          ),
        )
        ..add(
          _rowsSliver(
            count: rest.length,
            revealOffset: revealIndex,
            builder: (index) => SourceRowCard(
              source: rest[index],
              onTap: () => _open(rest[index]),
            ),
          ),
        );
    }

    return slivers;
  }

  void _open(SourceSummary source) =>
      context.go(RoutePaths.sourceBrowse(source.id));

  static SourceSummary _placeholderSource(SourcePin pin) => SourceSummary(
        id: pin.sourceId,
        name: pin.name,
        description: '',
        browsable: false,
        supportsImport: false,
        mature: pin.mature,
        iconUrl: pin.iconUrl,
      );

  static bool _matches(
    SourceSummary source,
    String query,
    SourcesFilter filter,
  ) {
    if (filter == SourcesFilter.mature && !source.mature) return false;
    if (query.isEmpty) return true;
    return source.name.toLowerCase().contains(query) ||
        source.id.toLowerCase().contains(query);
  }

  Widget _rowsSliver({
    required int count,
    required int revealOffset,
    required Widget Function(int index) builder,
  }) {
    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      sliver: SliverList.separated(
        itemCount: count,
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          // Stagger only the first screenful. The old `(index % 12) * 35`
          // restarted the ramp four times on the way down a 50-item list, so
          // rows kept fading in long after the intro should have finished.
          final position = revealOffset + index;
          return FadeIn(
            delay: Duration(milliseconds: position < 8 ? position * 40 : 0),
            offset: const Offset(0, 12),
            child: builder(index),
          );
        },
      ),
    );
  }
}

/// Pinned filter bar: the free-text field (with 50 sources, the single
/// highest-value control on this screen) plus the All/Pinned/18+ scope chips.
class _SourcesFilterBar extends SliverPersistentHeaderDelegate {
  const _SourcesFilterBar({
    required this.controller,
    required this.query,
    required this.filter,
    required this.pinnedCount,
    required this.onQueryChanged,
    required this.onFilterChanged,
  });

  final TextEditingController controller;
  final String query;
  final SourcesFilter filter;
  final int pinnedCount;
  final ValueChanged<String> onQueryChanged;
  final ValueChanged<SourcesFilter> onFilterChanged;

  // Every part below has a declared height, so the delegate's extent is exact
  // and cannot be knocked out of sync by input/chip theming.
  static const double _fieldHeight = 48;
  static const double _gap = AppSpacing.sm;
  static const double _topPad = AppSpacing.xs;
  static const double _bottomPad = AppSpacing.md;
  static const double _extent =
      _topPad + _fieldHeight + _gap + FilterPill.height + _bottomPad;

  @override
  double get minExtent => _extent;

  @override
  double get maxExtent => _extent;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    return Container(
      height: _extent,
      color: context.colors.bg,
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        _topPad,
        AppSpacing.lg,
        _bottomPad,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: _fieldHeight,
            child: TextField(
              controller: controller,
              onChanged: onQueryChanged,
              textInputAction: TextInputAction.search,
              style: AppTypography.body,
              decoration: InputDecoration(
                isDense: true,
                prefixIcon: Icon(Icons.search, color: context.colors.muted),
                prefixIconConstraints:
                    const BoxConstraints(minWidth: 44, minHeight: 44),
                suffixIcon: query.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close, size: 18),
                        color: context.colors.muted,
                        onPressed: () {
                          controller.clear();
                          onQueryChanged('');
                        },
                      ),
                hintText: 'Filter sources…',
                filled: true,
                fillColor: context.colors.fg.withAlpha(8),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppRadius.xl),
                  borderSide: BorderSide(color: context.colors.border.withAlpha(128)),
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppRadius.xl),
                  borderSide: BorderSide(color: context.colors.border.withAlpha(128)),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(AppRadius.xl),
                  borderSide: BorderSide(color: context.colors.primary.withAlpha(77)),
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.md,
                ),
              ),
            ),
          ),
          const SizedBox(height: _gap),
          SizedBox(
            height: FilterPill.height,
            child: ListView(
              scrollDirection: Axis.horizontal,
              children: [
                FilterPill(
                  label: 'All',
                  selected: filter == SourcesFilter.all,
                  onTap: () => onFilterChanged(SourcesFilter.all),
                ),
                const SizedBox(width: AppSpacing.sm),
                FilterPill(
                  label: 'Pinned',
                  count: pinnedCount,
                  selected: filter == SourcesFilter.pinned,
                  onTap: () => onFilterChanged(SourcesFilter.pinned),
                ),
                const SizedBox(width: AppSpacing.sm),
                FilterPill(
                  label: '18+',
                  selected: filter == SourcesFilter.mature,
                  onTap: () => onFilterChanged(SourcesFilter.mature),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  bool shouldRebuild(_SourcesFilterBar old) =>
      old.query != query ||
      old.filter != filter ||
      old.pinnedCount != pinnedCount ||
      old.controller != controller;
}

class _SectionHeaderSliver extends StatelessWidget {
  const _SectionHeaderSliver({required this.icon, required this.title});

  final IconData icon;
  final String title;

  @override
  Widget build(BuildContext context) {
    return SliverPadding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.sm,
        AppSpacing.lg,
        0,
      ),
      sliver: SliverToBoxAdapter(
        child: SectionHeader(icon: icon, title: title),
      ),
    );
  }
}

class _SourcesSkeletonSliver extends StatelessWidget {
  const _SourcesSkeletonSliver();

  @override
  Widget build(BuildContext context) {
    return SliverPadding(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      sliver: SliverList.separated(
        itemCount: 8,
        separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
        itemBuilder: (_, __) => const SourceRowSkeleton(),
      ),
    );
  }
}

class _SourcesErrorSliver extends StatelessWidget {
  const _SourcesErrorSliver({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return SliverFillRemaining(
      hasScrollBody: false,
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.xl2),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                message,
                textAlign: TextAlign.center,
                style: AppTypography.body.copyWith(color: context.colors.danger),
              ),
              const SizedBox(height: AppSpacing.lg),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      ),
    );
  }
}
