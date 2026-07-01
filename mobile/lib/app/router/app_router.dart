import 'package:aistudio_mobile/app/router/routes.dart';
import 'package:aistudio_mobile/features/library/screens/dashboard_screen.dart';
import 'package:aistudio_mobile/features/library/screens/library_screen.dart';
import 'package:aistudio_mobile/features/library/screens/series_detail_screen.dart';
import 'package:aistudio_mobile/shared/screens/placeholder_screen.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Application router — all screens registered here.
///
/// Feature screens replace the [PlaceholderScreen] as they are built.
final appRouter = GoRouter(
  initialLocation: Routes.home,
  debugLogDiagnostics: true,
  routes: [
    // ── Shell with bottom-nav ──────────────────────────────────────────────
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) =>
          _AppShell(navigationShell: navigationShell),
      branches: [
        // 0 — Library
        StatefulShellBranch(
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
                  path: ':seriesId',
                  builder: (context, state) => SeriesDetailScreen(
                    seriesId: int.parse(state.pathParameters['seriesId']!),
                  ),
                  routes: [
                    GoRoute(
                      path: 'chapters/:chapterId/read',
                      builder: (context, state) => PlaceholderScreen(
                        label:
                            'Reader ch:${state.pathParameters['chapterId']}',
                      ),
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
              builder: (context, state) => const PlaceholderScreen(label: 'Collections'),
              routes: [
                GoRoute(
                  path: ':collectionId',
                  builder: (context, state) => PlaceholderScreen(
                    label: 'Collection ${state.pathParameters['collectionId']}',
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
              builder: (context, state) => const PlaceholderScreen(label: 'Sources'),
              routes: [
                GoRoute(
                  path: ':sourceId',
                  builder: (context, state) => PlaceholderScreen(
                    label: 'Source ${state.pathParameters['sourceId']}',
                  ),
                  routes: [
                    GoRoute(
                      path: 'series/:seriesId',
                      builder: (context, state) => PlaceholderScreen(
                        label: 'Source Series ${state.pathParameters['seriesId']}',
                      ),
                      routes: [
                        GoRoute(
                          path: 'chapters/:chapterId/read',
                          builder: (context, state) => PlaceholderScreen(
                            label:
                                'Source Reader ${state.pathParameters['chapterId']}',
                          ),
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
              builder: (context, state) => const PlaceholderScreen(label: 'Downloads'),
            ),
          ],
        ),

        // 4 — Search
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: Routes.search,
              builder: (context, state) => const PlaceholderScreen(label: 'Search'),
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
      builder: (context, state) => const PlaceholderScreen(label: 'Updates'),
    ),
    GoRoute(
      path: Routes.settings,
      builder: (context, state) => const PlaceholderScreen(label: 'Settings'),
    ),
  ],
);

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
