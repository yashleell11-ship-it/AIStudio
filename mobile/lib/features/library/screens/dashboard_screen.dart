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
import 'package:manhwamaniacs/features/library/models/followed_series.dart';
import 'package:manhwamaniacs/features/library/widgets/home/followed_series_card.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_switcher_chip.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/scroll_reveal.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Library tab — the followed series, and nothing else.
///
/// Deliberately spare (DESIGN_SYSTEM.md hard constraint: "Library tab (mobile)
/// = followed series only"): one heading, one grid of covers. Tapping a card
/// opens that series' detail screen, where the full chapter list lives with the
/// latest chapter first. Browse Sources is reachable from exactly one place at
/// a time — the empty state when there is nothing followed yet, otherwise the
/// small app-bar action.
class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    // Dismiss any download queue snackbar left over from series detail.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ScaffoldMessenger.maybeOf(context)?.clearSnackBars();
    });
  }

  Future<void> _refresh() => ref.read(updatesProvider.notifier).refresh();

  @override
  Widget build(BuildContext context) {
    final updatesAsync = ref.watch(updatesProvider);
    // Resolved once so the app bar and the body agree on whether the shelf is
    // empty (and therefore on which single Browse affordance is shown).
    final followed = _followedOf(updatesAsync.valueOrNull);

    return Scaffold(
      // Float the active-profile chip (Netflix-style) over the top-right of the
      // grid without pushing the heading down.
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        toolbarHeight: kToolbarHeight,
        automaticallyImplyLeading: false,
        actions: [
          // The single Browse affordance once the shelf has something on it —
          // with an empty shelf the empty state owns that job instead, so the
          // screen never shows two routes to the same place.
          if (followed.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.travel_explore_rounded),
              tooltip: 'Browse Sources',
              onPressed: () => context.go(Routes.sources),
            ),
          const ProfileSwitcherChip(),
          const SizedBox(width: AppSpacing.sm),
        ],
      ),
      body: updatesAsync.when(
        loading: () => const _LibrarySkeleton(),
        error: (error, _) => _FollowedSeriesError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.invalidate(updatesProvider),
        ),
        data: (data) {
          if (followed.isEmpty) return _LibraryEmpty(onRefresh: _refresh);

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: _refresh,
            child: _FollowedGrid(
              followed: followed,
              notifications: data.notifications,
              onOpenSeries: (series) => _openSeries(context, series),
            ),
          );
        },
      ),
    );
  }

  List<FollowedSeries> _followedOf(UpdatesState? state) =>
      state?.followed ?? const [];

  void _openSeries(BuildContext context, FollowedSeries series) {
    context.push(
      RoutePaths.sourceSeriesDetail(series.sourceId, series.seriesKey),
    );
  }
}

/// The whole screen body: a heading and the followed-series cover grid.
class _FollowedGrid extends StatelessWidget {
  const _FollowedGrid({
    required this.followed,
    required this.notifications,
    required this.onOpenSeries,
  });

  final List<FollowedSeries> followed;
  final List<UpdateNotification> notifications;
  final void Function(FollowedSeries) onOpenSeries;

  @override
  Widget build(BuildContext context) {
    final bottomPad = MediaQuery.paddingOf(context).bottom;

    return CustomScrollView(
      // Always scrollable so pull-to-refresh still works with a single follow
      // that doesn't fill the viewport.
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            _headingTopPadding(context),
            AppSpacing.xl2,
            AppSpacing.xl,
          ),
          sliver: SliverToBoxAdapter(
            child: FadeIn(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const HeroHeading(text: 'Library', fontSize: 40),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    followed.length == 1
                        ? '1 series followed'
                        : '${followed.length} series followed',
                    style:
                        AppTypography.caption.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
          sliver: SliverGrid.builder(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: context.seriesGridColumns,
              crossAxisSpacing: AppSpacing.md,
              mainAxisSpacing: AppSpacing.xl,
              childAspectRatio: 0.5,
            ),
            itemCount: followed.length,
            itemBuilder: (context, index) {
              final series = followed[index];
              return ScrollReveal(
                index: index,
                child: FollowedSeriesCard(
                  series: series,
                  meta: FollowedSeriesMeta.forSeries(
                    series: series,
                    notifications: notifications,
                  ),
                  onTap: () => onOpenSeries(series),
                ),
              );
            },
          ),
        ),
        SliverToBoxAdapter(
          child: SizedBox(height: AppSpacing.xl6 + bottomPad),
        ),
      ],
    );
  }
}

/// Clears the transparent app bar the body is drawn behind.
double _headingTopPadding(BuildContext context) =>
    MediaQuery.paddingOf(context).top + kToolbarHeight + AppSpacing.lg;

/// Empty shelf — every account on this server starts here, so it has to say
/// what to do and offer the one way to do it.
class _LibraryEmpty extends StatelessWidget {
  const _LibraryEmpty({required this.onRefresh});

  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      color: AppColors.primary,
      onRefresh: onRefresh,
      child: CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverFillRemaining(
            hasScrollBody: false,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.xl3),
              child: Center(
                child: EmptyState(
                  icon: Icons.menu_book_outlined,
                  message: 'Your library is empty',
                  subtitle:
                      'Follow series from Sources to build your warm little shelf.',
                  action: PrimaryPillButton(
                    label: 'Browse Sources',
                    icon: Icons.travel_explore_rounded,
                    onPressed: () => context.go(Routes.sources),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Loading shimmer shaped like the real grid, so nothing shifts on load.
class _LibrarySkeleton extends StatelessWidget {
  const _LibrarySkeleton();

  @override
  Widget build(BuildContext context) {
    return CustomScrollView(
      physics: const NeverScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.xl2,
            _headingTopPadding(context),
            AppSpacing.xl2,
            AppSpacing.xl,
          ),
          sliver: const SliverToBoxAdapter(
            child: SkeletonBox(width: 200, height: 40),
          ),
        ),
        SliverPadding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl2),
          sliver: SliverGrid.builder(
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: context.seriesGridColumns,
              crossAxisSpacing: AppSpacing.md,
              mainAxisSpacing: AppSpacing.xl,
              childAspectRatio: 0.5,
            ),
            itemCount: 6,
            itemBuilder: (_, __) => const SkeletonBox(
              width: double.infinity,
              height: double.infinity,
              borderRadius: AppRadius.xl,
            ),
          ),
        ),
      ],
    );
  }
}

class _FollowedSeriesError extends StatelessWidget {
  const _FollowedSeriesError({
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
            Container(
              width: 72,
              height: 72,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.danger.withValues(alpha: 0.08),
              ),
              child: const Icon(Icons.error_outline, color: AppColors.danger, size: 32),
            ),
            const SizedBox(height: AppSpacing.xl2),
            const HeroHeading(text: 'Oops', fontSize: 40, textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.sm),
            Text(
              error.userMessage,
              style: AppTypography.body.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl3),
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
