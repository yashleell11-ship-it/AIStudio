import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/features/library/screens/bookmarks_screen.dart';
import 'package:aistudio_mobile/features/library/screens/dashboard_screen.dart';
import 'package:aistudio_mobile/features/library/screens/library_screen.dart';
import 'package:aistudio_mobile/features/library/screens/series_detail_screen.dart';
import 'package:aistudio_mobile/features/reader/screens/reader_screen.dart';
import 'package:aistudio_mobile/features/collections/screens/collection_detail_screen.dart';
import 'package:aistudio_mobile/features/collections/screens/collections_screen.dart';
import 'package:aistudio_mobile/features/downloads/screens/downloads_screen.dart';
import 'package:aistudio_mobile/features/library/screens/search_screen.dart';
import 'package:aistudio_mobile/features/library/screens/reading_history_screen.dart';
import 'package:aistudio_mobile/features/library/screens/recommendations_screen.dart';
import 'package:aistudio_mobile/features/library/screens/statistics_screen.dart';
import 'package:aistudio_mobile/features/setup/screens/setup_screen.dart';
import 'package:aistudio_mobile/features/settings/providers/settings_provider.dart';
import 'package:aistudio_mobile/features/settings/screens/settings_screen.dart';
import 'package:aistudio_mobile/features/sources/screens/source_browser_screen.dart';
import 'package:aistudio_mobile/features/sources/screens/source_reader_screen.dart';
import 'package:aistudio_mobile/features/sources/screens/source_series_detail_screen.dart';
import 'package:aistudio_mobile/features/sources/screens/sources_list_screen.dart';
import 'package:aistudio_mobile/features/updates/screens/updates_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');
final _shellNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'shell');

/// Application router — all screens registered here.
///
/// Feature screens replace the [PlaceholderScreen] as they are built.
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
                      builder: (context, state) {
                        final pageParam = state.uri.queryParameters['page'];
                        final initialPage =
                            pageParam != null ? int.tryParse(pageParam) ?? 1 : 1;
                        return ReaderScreen(
                          seriesId: int.parse(state.pathParameters['seriesId']!),
                          chapterId: int.parse(state.pathParameters['chapterId']!),
                          initialPage: initialPage,
                        );
                      },
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),

        // 1 — Collections
        StatefulShellBranch(
          routes: [
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
        ),

        // 2 — Sources
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
                          builder: (context, state) {
                            final pageParam =
                                state.uri.queryParameters['page'];
                            final initialPage = pageParam != null
                                ? int.tryParse(pageParam) ?? 1
                                : 1;
                            return SourceReaderScreen(
                              sourceId: state.pathParameters['sourceId']!,
                              seriesId: state.pathParameters['seriesId']!,
                              chapterId: state.pathParameters['chapterId']!,
                              initialPage: initialPage,
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

        // 3 — Downloads
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: Routes.downloads,
              builder: (context, state) => const DownloadsScreen(),
            ),
          ],
        ),

        // 4 — Search
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: Routes.search,
              builder: (context, state) => const SearchScreen(),
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
      path: Routes.setup,
      builder: (context, state) => const SetupScreen(),
    ),
  ],
  );
});

/// Bottom-navigation shell shared by the main tab branches.
class _AppShell extends StatelessWidget {
  const _AppShell({required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: navigationShell.goBranch,
        destinations: const [
          NavigationDestination(icon: Icon(Icons.menu_book), label: 'Library'),
          NavigationDestination(icon: Icon(Icons.collections_bookmark), label: 'Collections'),
          NavigationDestination(icon: Icon(Icons.public), label: 'Sources'),
          NavigationDestination(icon: Icon(Icons.download), label: 'Downloads'),
          NavigationDestination(icon: Icon(Icons.search), label: 'Search'),
        ],
      ),
    );
  }
}
