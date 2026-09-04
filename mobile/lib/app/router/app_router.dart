import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/auth/models/auth_state.dart';
import 'package:manhwamaniacs/features/auth/providers/auth_controller.dart';
import 'package:manhwamaniacs/features/auth/screens/login_screen.dart';
import 'package:manhwamaniacs/features/auth/screens/register_screen.dart';
import 'package:manhwamaniacs/features/auth/screens/splash_screen.dart';
import 'package:manhwamaniacs/features/collections/screens/collection_detail_screen.dart';
import 'package:manhwamaniacs/features/collections/screens/collections_screen.dart';
import 'package:manhwamaniacs/features/downloads/providers/active_download_queue_provider.dart';
import 'package:manhwamaniacs/features/downloads/screens/downloads_screen.dart';
import 'package:manhwamaniacs/features/library/screens/bookmarks_screen.dart';
import 'package:manhwamaniacs/features/library/screens/dashboard_screen.dart';
import 'package:manhwamaniacs/features/library/screens/library_screen.dart';
import 'package:manhwamaniacs/features/library/screens/reading_history_screen.dart';
import 'package:manhwamaniacs/features/library/screens/recommendations_screen.dart';
import 'package:manhwamaniacs/features/library/screens/search_screen.dart';
import 'package:manhwamaniacs/features/library/screens/series_detail_screen.dart';
import 'package:manhwamaniacs/features/library/screens/statistics_screen.dart';
import 'package:manhwamaniacs/features/more/screens/more_screen.dart';
import 'package:manhwamaniacs/features/novels/screens/novel_reader_screen.dart';
import 'package:manhwamaniacs/features/ocr/screens/ocr_search_screen.dart';
import 'package:manhwamaniacs/features/profiles/models/mood.dart';
import 'package:manhwamaniacs/features/profiles/profile_routes.dart';
import 'package:manhwamaniacs/features/profiles/providers/profiles_providers.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_create_screen.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_edit_screen.dart';
import 'package:manhwamaniacs/features/profiles/screens/profile_picker_screen.dart';
import 'package:manhwamaniacs/features/profiles/widgets/mood_backdrop.dart';
import 'package:manhwamaniacs/features/reader/screens/reader_screen.dart';
import 'package:manhwamaniacs/features/settings/providers/settings_provider.dart';
import 'package:manhwamaniacs/features/settings/screens/backup_screen.dart';
import 'package:manhwamaniacs/features/settings/screens/diagnostics_screen.dart';
import 'package:manhwamaniacs/features/settings/screens/settings_screen.dart';
import 'package:manhwamaniacs/features/settings/screens/storage_screen.dart';
import 'package:manhwamaniacs/features/setup/screens/setup_screen.dart';
import 'package:manhwamaniacs/features/sources/screens/source_browser_screen.dart';
import 'package:manhwamaniacs/features/sources/screens/source_reader_screen.dart';
import 'package:manhwamaniacs/features/sources/screens/source_series_detail_screen.dart';
import 'package:manhwamaniacs/features/sources/screens/sources_list_screen.dart';
import 'package:manhwamaniacs/features/updates/screens/updates_screen.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');
final _shellNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'shell');

/// Application router — all screens registered here.
final appRouterProvider = Provider<GoRouter>((ref) {
  final setupCompleted = ref.watch(setupCompletedProvider);
  // Recreated whenever auth transitions (unknown → un/authenticated, login,
  // logout) so the redirect below re-runs from the initial location — exactly
  // the moments where a full navigation reset is desired.
  final authState = ref.watch(authControllerProvider);
  // Recreate when the profile session gate opens/closes so cold starts land on
  // the picker until a profile is chosen for this session.
  final profileSessionReady = ref.watch(profileSessionReadyProvider);
  // Keep the X-Profile-Id header in sync with the active profile for the app's
  // lifetime; watching it here means it is always installed while the router is.
  ref.watch(profileHeaderSyncProvider);

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: Routes.home,
    debugLogDiagnostics: true,
    redirect: (context, state) {
      final path = state.uri.path;

      // 1) Setup (server URL) gate — must resolve before auth.
      if (!setupCompleted) {
        return path == Routes.setup ? null : Routes.setup;
      }

      // 2) Auth gate.
      final onAuthRoute = path == Routes.login || path == Routes.register;
      final onSplash = path == Routes.splash;
      final onSetup = path == Routes.setup;
      // The profile picker/create/edit surface (the post-auth persona gate).
      final onProfileRoute = path == ProfileRoutes.picker ||
          path.startsWith('${ProfileRoutes.picker}/');

      return switch (authState) {
        // Cold start: hold on the splash while the stored token is validated.
        AuthUnknown() => onSplash ? null : Routes.splash,
        // No session: force the login/register flow.
        AuthUnauthenticated() => onAuthRoute ? null : Routes.login,
        // Signed in: show the profile picker once per app session (Netflix-style)
        // before the main shell. Create/edit routes stay reachable mid-gate.
        AuthAuthenticated() when !profileSessionReady =>
          onProfileRoute ? null : ProfileRoutes.picker,
        AuthAuthenticated() =>
          (onAuthRoute || onSplash || onSetup) ? Routes.home : null,
      };
    },
    routes: [
      // ── Authentication (full-screen, outside the tab shell) ────────────────
      GoRoute(
        path: Routes.splash,
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: Routes.login,
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: Routes.register,
        builder: (context, state) => const RegisterScreen(),
      ),
      // ── Shell with bottom-nav ──────────────────────────────────────────────
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            _AppShell(navigationShell: navigationShell),
        branches: [
          // 0 — Library
          StatefulShellBranch(
            navigatorKey: _shellNavigatorKey,
            routes: [
              GoRoute(
                path: Routes.library,
                builder: (context, state) => const DashboardScreen(),
                routes: [
                  GoRoute(
                    path: 'browse',
                    builder: (context, state) => const LibraryScreen(),
                  ),
                  GoRoute(
                    path: 'recommendations',
                    builder: (context, state) => const RecommendationsScreen(),
                  ),
                  GoRoute(
                    path: 'statistics',
                    builder: (context, state) => const StatisticsScreen(),
                  ),
                  GoRoute(
                    path: 'history',
                    builder: (context, state) => const ReadingHistoryScreen(),
                  ),
                  GoRoute(
                    path: 'bookmarks',
                    builder: (context, state) => const BookmarksScreen(),
                  ),
                  GoRoute(
                    path: ':seriesId',
                    builder: (context, state) => SeriesDetailScreen(
                      seriesId: int.parse(state.pathParameters['seriesId']!),
                    ),
                  ),
                  // The manifest-driven reader — keyed by the opaque
                  // (sourceId, seriesKey, chapterKey) triple, not the follow
                  // row id, so it is reachable from continue-reading,
                  // bookmarks and history without a lookup (see Routes.reader).
                  GoRoute(
                    path: 'read/:sourceId/:seriesKey/:chapterKey',
                    parentNavigatorKey: _rootNavigatorKey,
                    pageBuilder: (context, state) {
                      final pageParam = state.uri.queryParameters['page'];
                      final initialPage = pageParam != null
                          ? int.tryParse(pageParam) ?? 1
                          : 1;
                      return _immersiveReaderPage(
                        ReaderScreen(
                          sourceId: state.pathParameters['sourceId']!,
                          seriesKey: state.pathParameters['seriesKey']!,
                          chapterKey: state.pathParameters['chapterKey']!,
                          initialPage: initialPage,
                        ),
                      );
                    },
                  ),
                ],
              ),
            ],
          ),

          // 1 — Sources
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.sources,
                builder: (context, state) => const SourcesListScreen(),
                routes: [
                  GoRoute(
                    path: ':sourceId',
                    builder: (context, state) => SourceBrowserScreen(
                      sourceId: state.pathParameters['sourceId']!,
                    ),
                    routes: [
                      GoRoute(
                        path: 'series/:seriesId',
                        builder: (context, state) => SourceSeriesDetailScreen(
                          sourceId: state.pathParameters['sourceId']!,
                          seriesId: state.pathParameters['seriesId']!,
                        ),
                        routes: [
                          GoRoute(
                            path: 'chapters/:chapterId/read',
                            parentNavigatorKey: _rootNavigatorKey,
                            pageBuilder: (context, state) {
                              final pageParam =
                                  state.uri.queryParameters['page'];
                              final initialPage = pageParam != null
                                  ? int.tryParse(pageParam) ?? 1
                                  : 1;
                              return _immersiveReaderPage(
                                SourceReaderScreen(
                                  sourceId: state.pathParameters['sourceId']!,
                                  seriesId: state.pathParameters['seriesId']!,
                                  chapterId:
                                      state.pathParameters['chapterId']!,
                                  initialPage: initialPage,
                                ),
                              );
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),

          // 2 — Search
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.search,
                builder: (context, state) => const SearchScreen(),
              ),
            ],
          ),

          // 3 — Downloads. A branch rather than a top-level route so the
          // bottom nav stays visible on it and its scroll position survives
          // a trip to another tab — an offline library is somewhere you dip
          // in and out of while reading, not a settings page you visit once.
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.downloads,
                builder: (context, state) => const DownloadsScreen(),
              ),
            ],
          ),

          // 4 — More
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.more,
                builder: (context, state) => const MoreScreen(),
              ),
            ],
          ),
        ],
      ),

      // ── Reading profiles (full-screen, outside the tab shell) ──────────────
      GoRoute(
        path: ProfileRoutes.picker,
        builder: (context, state) => const ProfilePickerScreen(),
      ),
      GoRoute(
        path: ProfileRoutes.create,
        builder: (context, state) => const ProfileCreateScreen(),
      ),
      GoRoute(
        path: ProfileRoutes.editPattern,
        builder: (context, state) => ProfileEditScreen(
          profileId: int.parse(state.pathParameters['id']!),
        ),
      ),

      // ── Top-level non-tab screens ──────────────────────────────────────────
      GoRoute(
        path: Routes.home,
        redirect: (_, __) => Routes.library,
      ),
      GoRoute(
        path: Routes.updates,
        builder: (context, state) => const UpdatesScreen(),
      ),
      GoRoute(
        path: Routes.settings,
        builder: (context, state) => const SettingsScreen(),
      ),
      GoRoute(
        path: Routes.diagnostics,
        builder: (context, state) => const DiagnosticsScreen(),
      ),
      GoRoute(
        path: Routes.backup,
        builder: (context, state) => const BackupScreen(),
      ),
      GoRoute(
        path: Routes.storage,
        builder: (context, state) => const StorageScreen(),
      ),
      GoRoute(
        path: Routes.ocrSearch,
        builder: (context, state) => const OcrSearchScreen(),
      ),
      // The novel reader — a root-navigator route with the same immersive
      // fade as the manga reader, so entering a chapter feels the same
      // whichever medium it is, and the bottom nav is gone either way.
      GoRoute(
        path: Routes.novelReader,
        parentNavigatorKey: _rootNavigatorKey,
        pageBuilder: (context, state) {
          // `?page=` carries the progress BUCKET, the same parameter and the
          // same 1-based meaning the manga reader gives a page number — so a
          // "Continue" link needs no novel-specific branch to build.
          final pageParam = state.uri.queryParameters['page'];
          final initialBucket =
              pageParam != null ? int.tryParse(pageParam) ?? 1 : 1;
          return _immersiveReaderPage(
            NovelReaderScreen(
              sourceId: state.pathParameters['sourceId']!,
              seriesKey: state.pathParameters['seriesKey']!,
              chapterKey: state.pathParameters['chapterKey']!,
              initialBucket: initialBucket,
            ),
          );
        },
      ),
      GoRoute(
        path: Routes.setup,
        builder: (context, state) => const SetupScreen(),
      ),
      // Collections is now a top-level route (accessible from More tab)
      GoRoute(
        path: Routes.collections,
        builder: (context, state) => const CollectionsScreen(),
        routes: [
          GoRoute(
            path: ':collectionId',
            builder: (context, state) => CollectionDetailScreen(
              collectionId: int.parse(state.pathParameters['collectionId']!),
            ),
          ),
        ],
      ),
    ],
  );
});

/// Immersive fade for entering and leaving the reader — feels more like
/// slipping into the page than a lateral push between screens.
CustomTransitionPage<void> _immersiveReaderPage(Widget child) {
  return CustomTransitionPage<void>(
    transitionDuration: const Duration(milliseconds: 280),
    reverseTransitionDuration: const Duration(milliseconds: 220),
    transitionsBuilder: (context, animation, secondaryAnimation, child) {
      return FadeTransition(
        opacity: CurvedAnimation(parent: animation, curve: Curves.easeOutCubic),
        child: child,
      );
    },
    child: child,
  );
}

/// Floating glass navigation shell.
class _AppShell extends ConsumerWidget {
  const _AppShell({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final location = GoRouterState.of(context).uri.path;
    final showBottomNav = isMainTabRoute(location);
    final bottomPad = MediaQuery.paddingOf(context).bottom;
    // The active profile's mood tints the whole app for the session; it sits
    // behind every tab and bleeds through the frosted nav bar. The reader
    // renders outside this shell (rootNavigatorKey) so it stays black.
    final mood = ref.watch(activeProfileProvider)?.mood ?? Mood.neutral;
    // The badge is the fix for "I tapped Download Series and nothing seemed
    // to happen": it makes an active queue visible from every other tab, not
    // only from the one screen that reports on it.
    final pendingDownloads = ref.watch(activeDownloadCountProvider);

    return MoodBackdrop(
      mood: mood,
      // variant defaults to MoodBackdropVariant.shell
      // Make the tab screens transparent (scoped to this subtree only) so the
      // mood backdrop shows through them. The theme's opaque scaffold colour
      // still applies outside the shell — reader, auth, setup, profile picker.
      child: Theme(
        data: Theme.of(context)
            .copyWith(scaffoldBackgroundColor: Colors.transparent),
        child: Scaffold(
        extendBody: showBottomNav,
        backgroundColor: Colors.transparent,
        body: navigationShell,
      bottomNavigationBar: showBottomNav
          ? Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.lg,
          0,
          AppSpacing.lg,
          bottomPad > 0 ? bottomPad : AppSpacing.sm,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.xl),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withAlpha(110),
                blurRadius: 20,
                offset: const Offset(0, 6),
              ),
              BoxShadow(
                color: context.colors.primary.withAlpha(24),
                blurRadius: 24,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.xl),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  // Eclipse Warm frosted glass: near-black surface at ~0.85
                  // alpha over the mood backdrop, with the subtle warm-neutral
                  // border edge.
                  color: context.colors.surface.withAlpha(217),
                  borderRadius: BorderRadius.circular(AppRadius.xl),
                  border: Border.all(color: context.colors.border),
                ),
                child: NavigationBarTheme(
                  // Active = amber (primary); inactive = muted. Icon colour on a
                  // NavigationBar is driven through its theme, not per-item.
                  data: NavigationBarThemeData(
                    iconTheme: WidgetStateProperty.resolveWith(
                      (states) => IconThemeData(
                        color: states.contains(WidgetState.selected)
                            ? context.colors.primary
                            : context.colors.muted,
                      ),
                    ),
                    labelTextStyle: WidgetStateProperty.resolveWith(
                      (states) {
                        // Inherit the DM Sans label style from the theme; only
                        // recolour + weight it per selection state.
                        final base = Theme.of(context).textTheme.labelMedium ??
                            const TextStyle();
                        final selected =
                            states.contains(WidgetState.selected);
                        return base.copyWith(
                          color: selected
                              ? context.colors.primary
                              : context.colors.muted,
                          fontWeight:
                              selected ? FontWeight.w600 : FontWeight.w500,
                        );
                      },
                    ),
                  ),
                  child: NavigationBar(
                    selectedIndex: navigationShell.currentIndex,
                    onDestinationSelected: navigationShell.goBranch,
                    backgroundColor: Colors.transparent,
                    surfaceTintColor: Colors.transparent,
                    shadowColor: Colors.transparent,
                    // Warm amber wash behind the active destination.
                    indicatorColor: context.colors.primary.withAlpha(30),
                    labelBehavior:
                        NavigationDestinationLabelBehavior.onlyShowSelected,
                    destinations: [
                    const NavigationDestination(
                      icon: Icon(Icons.menu_book_outlined),
                      selectedIcon: Icon(Icons.menu_book),
                      label: 'Library',
                    ),
                    const NavigationDestination(
                      icon: Icon(Icons.public_outlined),
                      selectedIcon: Icon(Icons.public),
                      label: 'Sources',
                    ),
                    const NavigationDestination(
                      icon: Icon(Icons.search_outlined),
                      selectedIcon: Icon(Icons.search),
                      label: 'Search',
                    ),
                    NavigationDestination(
                      icon: _DownloadsTabIcon(
                        icon: Icons.download_outlined,
                        count: pendingDownloads,
                      ),
                      selectedIcon: _DownloadsTabIcon(
                        icon: Icons.download,
                        count: pendingDownloads,
                      ),
                      label: 'Downloads',
                    ),
                    const NavigationDestination(
                      icon: Icon(Icons.more_horiz_outlined),
                      selectedIcon: Icon(Icons.more_horiz),
                      label: 'More',
                    ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      )
          : null,
    ),
    ),
  );
  }
}

/// The Downloads destination's icon, with a count badge while the queue has
/// work left. Hidden at zero rather than showing "0" — an idle queue is the
/// normal state and should not draw the eye.
class _DownloadsTabIcon extends StatelessWidget {
  const _DownloadsTabIcon({required this.icon, required this.count});

  final IconData icon;
  final int count;

  @override
  Widget build(BuildContext context) {
    return Badge.count(
      count: count,
      isLabelVisible: count > 0,
      backgroundColor: context.colors.primary,
      textColor: context.colors.primaryFg,
      child: Icon(icon),
    );
  }
}
