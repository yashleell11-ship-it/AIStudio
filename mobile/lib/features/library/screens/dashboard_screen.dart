import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_radius.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/app/theme/app_typography.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/features/library/models/continue_reading_item.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/providers/dashboard_providers.dart';
import 'package:manhwamaniacs/features/library/utils/cover_url.dart';
import 'package:manhwamaniacs/features/library/widgets/home/home_cover_marquee.dart';
import 'package:manhwamaniacs/features/library/widgets/home/home_sections.dart';
import 'package:manhwamaniacs/features/profiles/widgets/profile_switcher_chip.dart';
import 'package:manhwamaniacs/features/updates/models/series_tracker.dart';
import 'package:manhwamaniacs/features/updates/providers/updates_provider.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/widgets/empty_state.dart';
import 'package:manhwamaniacs/shared/widgets/premium/fade_in.dart';
import 'package:manhwamaniacs/shared/widgets/premium/hero_heading.dart';
import 'package:manhwamaniacs/shared/widgets/premium/primary_pill_button.dart';
import 'package:manhwamaniacs/shared/widgets/skeleton_box.dart';

/// Resume path for a library series+chapter (mirrors series-detail routing).
String _readerPath(int seriesId, int chapterId) =>
    '${RoutePaths.seriesDetail(seriesId)}/chapters/$chapterId/read';

/// Library tab home — an "Eclipse Warm" dashboard built over the user's
/// followed series (Library = followed only) enriched with continue-reading
/// and recently-updated data.
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

  Future<void> _refresh() async {
    ref.invalidate(dashboardProvider);
    await ref.read(updatesProvider.notifier).refresh();
  }

  @override
  Widget build(BuildContext context) {
    final updatesAsync = ref.watch(updatesProvider);

    return Scaffold(
      // Float the active-profile chip (Netflix-style) over the top-right of the
      // hero without disturbing the existing full-bleed hero layout.
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        toolbarHeight: kToolbarHeight,
        automaticallyImplyLeading: false,
        actions: const [
          ProfileSwitcherChip(),
          SizedBox(width: AppSpacing.sm),
        ],
      ),
      body: updatesAsync.when(
        loading: () => const _HomeSkeleton(),
        error: (error, _) => _FollowedSeriesError(
          error: error is AppError
              ? error
              : UnknownError(message: error.toString(), cause: error),
          onRetry: () => ref.invalidate(updatesProvider),
        ),
        data: (state) {
          final followed = state.trackers
              .where((tracker) => tracker.trackKind == TrackKind.followed)
              .toList();

          // Enrichment data (continue-reading + trending). Never blocks the
          // dashboard — if it errors or is loading we simply omit those bits.
          final dash = ref.watch(dashboardProvider).valueOrNull;
          final continueItems = dash?.continueReading ?? const [];
          final trending = dash?.recentlyUpdated ?? const [];

          if (followed.isEmpty && continueItems.isEmpty && trending.isEmpty) {
            return _HomeEmpty(onRefresh: _refresh);
          }

          return RefreshIndicator(
            color: AppColors.primary,
            onRefresh: _refresh,
            child: _HomeContent(
              followed: followed,
              continueItems: continueItems,
              trending: trending,
              onOpenTracker: (t) => _openTracker(context, t),
            ),
          );
        },
      ),
    );
  }

  void _openTracker(BuildContext context, SeriesTracker tracker) {
    final localId = tracker.localSeriesId;
    if (localId != null) {
      context.push(RoutePaths.seriesDetail(localId));
      return;
    }
    context.push(
      RoutePaths.sourceSeriesDetail(tracker.source, tracker.seriesId),
    );
  }
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent({
    required this.followed,
    required this.continueItems,
    required this.trending,
    required this.onOpenTracker,
  });

  final List<SeriesTracker> followed;
  final List<ContinueReadingItem> continueItems;
  final List<SeriesSummary> trending;
  final void Function(SeriesTracker) onOpenTracker;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final baseUrl = ref.watch(apiBaseUrlProvider);
    final topPad = MediaQuery.paddingOf(context).top;
    final bottomPad = MediaQuery.paddingOf(context).bottom;

    final firstContinue = continueItems.isNotEmpty ? continueItems.first : null;

    // Hero cover: the resume target, else the first followed/trending cover.
    String? heroCover;
    if (firstContinue != null) {
      heroCover = seriesCoverUrl(baseUrl, firstContinue.seriesId);
    } else {
      final firstFollowedCover = followed
          .map((t) => trackerCoverUrl(baseUrl, t))
          .whereType<String>()
          .firstOrNull;
      if (firstFollowedCover != null) {
        heroCover = firstFollowedCover;
      } else if (trending.isNotEmpty) {
        heroCover = seriesCoverUrl(baseUrl, trending.first.id);
      }
    }

    // Marquee covers: followed covers first, topped up with trending. Auth-gated
    // URLs rendered through SeriesCoverImage tiles inside HomeCoverMarquee.
    final marqueeCovers = <String>{
      for (final t in followed)
        if (trackerCoverUrl(baseUrl, t) case final url?) url,
      for (final s in trending) seriesCoverUrl(baseUrl, s.id),
    }.toList();

    final continueCards = _buildContinueCards(context, baseUrl);
    final sectionTitle = continueItems.isNotEmpty
        ? 'Continue'
        : trending.isNotEmpty
            ? 'Recently Updated'
            : 'Your Library';

    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: EdgeInsets.only(top: topPad + AppSpacing.xl2),
          sliver: SliverToBoxAdapter(
            child: FadeIn(
              child: HomeHero(
                heading: 'Your Library',
                tagline: firstContinue != null
                    ? 'Pick up where you left off'
                    : 'Your followed series, together',
                coverUrl: heroCover,
                ctaLabel:
                    firstContinue != null ? 'Continue Reading' : 'Browse Sources',
                ctaIcon: firstContinue != null
                    ? Icons.play_arrow_rounded
                    : Icons.travel_explore_rounded,
                onCta: () {
                  if (firstContinue != null) {
                    context.push(
                      _readerPath(
                        firstContinue.seriesId,
                        firstContinue.chapterId,
                      ),
                    );
                  } else {
                    context.go(Routes.sources);
                  }
                },
              ),
            ),
          ),
        ),
        if (marqueeCovers.isNotEmpty)
          SliverPadding(
            padding: const EdgeInsets.only(top: AppSpacing.xl3),
            sliver: SliverToBoxAdapter(
              child: HomeCoverMarquee(coverUrls: marqueeCovers),
            ),
          ),
        SliverPadding(
          padding: const EdgeInsets.only(top: AppSpacing.xl3),
          sliver: SliverToBoxAdapter(
            child: HomeAbout(onCta: () => context.go(Routes.sources)),
          ),
        ),
        if (continueCards.isNotEmpty) ...[
          SliverPadding(
            padding: const EdgeInsets.only(top: AppSpacing.xl3),
            sliver: SliverToBoxAdapter(
              child: HomeSectionLabel(text: sectionTitle),
            ),
          ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.xl2,
              AppSpacing.lg,
              AppSpacing.xl2,
              0,
            ),
            sliver: SliverList.separated(
              itemCount: continueCards.length,
              separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.md),
              itemBuilder: (context, index) => FadeIn(
                delay: Duration(milliseconds: 60 * index),
                child: continueCards[index],
              ),
            ),
          ),
        ],
        SliverToBoxAdapter(
          child: SizedBox(height: AppSpacing.xl6 + bottomPad),
        ),
      ],
    );
  }

  List<Widget> _buildContinueCards(BuildContext context, String baseUrl) {
    if (continueItems.isNotEmpty) {
      return [
        for (final item in continueItems)
          HomeContinueCard(
            coverUrl: seriesCoverUrl(baseUrl, item.seriesId),
            title: item.seriesTitle,
            subtitle: continueSubtitle(item),
            progressPct: item.progressPct,
            onTap: () =>
                context.push(_readerPath(item.seriesId, item.chapterId)),
          ),
      ];
    }
    if (trending.isNotEmpty) {
      return [
        for (final s in trending)
          HomeContinueCard(
            coverUrl: seriesCoverUrl(baseUrl, s.id),
            title: s.title,
            subtitle: '${s.readChapters}/${s.totalChapters} chapters',
            progressPct: s.totalChapters > 0 ? s.readProgressPct * 100 : null,
            onTap: () => context.push(RoutePaths.seriesDetail(s.id)),
          ),
      ];
    }
    return [
      // Every followed series — local imports AND online-only follows. Online
      // follows resolve to their source cover; only a genuinely unresolvable
      // tracker falls through to the placeholder inside HomeContinueCard.
      for (final t in followed)
        HomeContinueCard(
          coverUrl: trackerCoverUrl(baseUrl, t) ?? '',
          title: t.seriesTitle,
          subtitle: '${t.knownChapterCount} chapters',
          onTap: () => onOpenTracker(t),
        ),
    ];
  }
}

/// Welcome state for a fresh account with nothing followed or in progress.
class _HomeEmpty extends StatelessWidget {
  const _HomeEmpty({required this.onRefresh});

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

class _HomeSkeleton extends StatelessWidget {
  const _HomeSkeleton();

  @override
  Widget build(BuildContext context) {
    final topPad = MediaQuery.paddingOf(context).top;

    return ListView(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.xl2,
        topPad + AppSpacing.xl2,
        AppSpacing.xl2,
        AppSpacing.xl6,
      ),
      physics: const NeverScrollableScrollPhysics(),
      children: const [
        SkeletonBox(width: 220, height: 56),
        SizedBox(height: AppSpacing.xl2),
        Center(
          child: SkeletonBox(width: 168, height: 252, borderRadius: AppRadius.xl2),
        ),
        SizedBox(height: AppSpacing.xl2),
        SkeletonBox(width: 200, height: 16),
        SizedBox(height: AppSpacing.lg),
        SkeletonBox(width: 200, height: 48, borderRadius: AppRadius.pill),
        SizedBox(height: AppSpacing.xl3),
        SizedBox(
          height: 168,
          child: Row(
            children: [
              SkeletonBox(width: 112, height: 168, borderRadius: AppRadius.lg),
              SizedBox(width: AppSpacing.md),
              SkeletonBox(width: 112, height: 168, borderRadius: AppRadius.lg),
              SizedBox(width: AppSpacing.md),
              SkeletonBox(width: 112, height: 168, borderRadius: AppRadius.lg),
            ],
          ),
        ),
        SizedBox(height: AppSpacing.xl3),
        SkeletonBox(width: double.infinity, height: 150, borderRadius: AppRadius.xl2),
        SizedBox(height: AppSpacing.xl3),
        SkeletonBox(width: double.infinity, height: 102, borderRadius: AppRadius.xl),
        SizedBox(height: AppSpacing.md),
        SkeletonBox(width: double.infinity, height: 102, borderRadius: AppRadius.xl),
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
