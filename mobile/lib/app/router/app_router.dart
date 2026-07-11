import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/app/router/routes.dart';
import 'package:manhwamaniacs/app/theme/app_colors.dart';
import 'package:manhwamaniacs/app/theme/app_spacing.dart';
import 'package:manhwamaniacs/features/collections/screens/collection_detail_screen.dart';
import 'package:manhwamaniacs/features/collections/screens/collections_screen.dart';
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

  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: Routes.home,
    debugLogDiagnostics: true,
    redirect: (context, state) {
      final onSetup = state.uri.path == Routes.setup;
      if (!setupCompleted && !onSetup) return Routes.setup;
      if (setupCompleted && onSetup) return Routes.library;
      return null;
    },
    routes: [
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
                    routes: [
                      GoRoute(
                        path: 'chapters/:chapterId/read',
                        parentNavigatorKey: _rootNavigatorKey,
                        pageBuilder: (context, state) {
                          final pageParam = state.uri.queryParameters['page'];
                          final initialPage = pageParam != null
                              ? int.tryParse(pageParam) ?? 1
                              : 1;
                          return _immersiveReaderPage(
                            ReaderScreen(
                              seriesId:
                                  int.parse(state.pathParameters['seriesId']!),
                              chapterId:
                                  int.parse(state.pathParameters['chapterId']!),
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

          // 2 — Downloads
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.downloads,
                builder: (context, state) => const DownloadsScreen(),
              ),
            ],
          ),

          // 3 — Search
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: Routes.search,
                builder: (context, state) => const SearchScreen(),
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
class _AppShell extends StatelessWidget {
  const _AppShell({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final bottomPad = MediaQuery.paddingOf(context).bottom;

    return Scaffold(
      extendBody: true,
      body: navigationShell,
      bottomNavigationBar: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.xl2,
          0,
          AppSpacing.xl2,
          (bottomPad > 0 ? bottomPad : AppSpacing.lg),
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppRadius.xl2),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withAlpha(110),
                blurRadius: 28,
                offset: const Offset(0, 10),
              ),
              BoxShadow(
                color: AppColors.primary.withAlpha(24),
                blurRadius: 36,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppRadius.xl2),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: AppColors.sidebar.withAlpha(214),
                  borderRadius: BorderRadius.circular(AppRadius.xl2),
                  border: Border.all(color: AppColors.glassEdge),
                ),
                child: NavigationBar(
                  selectedIndex: navigationShell.currentIndex,
                  onDestinationSelected: navigationShell.goBranch,
                  backgroundColor: Colors.transparent,
                  surfaceTintColor: Colors.transparent,
                  shadowColor: Colors.transparent,
                  destinations: const [
                    NavigationDestination(
                      icon: Icon(Icons.menu_book_outlined),
                      selectedIcon: Icon(Icons.menu_book),
                      label: 'Library',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.public_outlined),
                      selectedIcon: Icon(Icons.public),
                      label: 'Sources',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.download_outlined),
                      selectedIcon: Icon(Icons.download),
                      label: 'Downloads',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.search_outlined),
                      selectedIcon: Icon(Icons.search),
                      label: 'Search',
                    ),
                    NavigationDestination(
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
    );
  }
}
