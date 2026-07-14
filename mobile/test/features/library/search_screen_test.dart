import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';
import 'package:manhwamaniacs/features/library/repositories/global_search_repository.dart';
import 'package:manhwamaniacs/features/library/screens/search_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Fake federated-search repo. Returns [result] for a non-empty query, or an
/// [error] when configured to fail.
class _FakeGlobalSearchRepository implements GlobalSearchRepository {
  _FakeGlobalSearchRepository({this.result, this.error});

  final GlobalSearchResult? result;
  final AppError? error;

  @override
  Future<Result<GlobalSearchResult>> search(
    String query, {
    int page = 1,
    int perPage = 40,
  }) async {
    if (error != null) return Err(error!);
    return Ok(result ?? const GlobalSearchResult());
  }
}

Future<void> _pumpSearch(
  WidgetTester tester,
  GlobalSearchRepository repo,
) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  final router = GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, __) => const SearchScreen()),
      GoRoute(
        path: '/library/:seriesId',
        builder: (_, state) =>
            Scaffold(body: Text('LOCAL ${state.pathParameters['seriesId']}')),
      ),
      GoRoute(
        path: '/sources/:sourceId/series/:seriesId',
        builder: (_, state) => Scaffold(
          body: Text(
            'SOURCE ${state.pathParameters['sourceId']} '
            '${state.pathParameters['seriesId']}',
          ),
        ),
      ),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        globalSearchRepositoryProvider.overrideWithValue(repo),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _search(WidgetTester tester, String term) async {
  await tester.enterText(find.byType(TextField), term);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SearchScreen (federated)', () {
    testWidgets('shows suggestions before searching', (tester) async {
      await _pumpSearch(tester, _FakeGlobalSearchRepository());

      expect(find.text('Start typing to search'), findsOneWidget);
      expect(find.text('TRENDING'), findsOneWidget);
      expect(find.text('fantasy'), findsOneWidget);
    });

    testWidgets('renders merged local + source results with badges',
        (tester) async {
      await _pumpSearch(
        tester,
        _FakeGlobalSearchRepository(
          result: const GlobalSearchResult(
            items: [
              GlobalSearchItem(
                kind: 'local',
                seriesId: '1',
                title: 'One Piece (Library)',
              ),
              GlobalSearchItem(
                kind: 'source',
                source: 'mangadex',
                seriesId: 'md-1',
                title: 'One Piece (MangaDex)',
              ),
            ],
            sourcesQueried: 12,
            sourcesFailed: 1,
          ),
        ),
      );

      await _search(tester, 'one piece');

      expect(find.text('One Piece (Library)'), findsOneWidget);
      expect(find.text('One Piece (MangaDex)'), findsOneWidget);
      // Badges: LIBRARY for the local hit, MANGADEX for the source hit.
      expect(find.text('LIBRARY'), findsOneWidget);
      expect(find.text('MANGADEX'), findsOneWidget);
      // Status line reflects sources queried, and flags failures subtly.
      expect(find.textContaining('2 results found'), findsOneWidget);
      expect(find.text('Some sources unavailable'), findsOneWidget);
    });

    testWidgets('empty result shows "No results found", not a spinner',
        (tester) async {
      await _pumpSearch(
        tester,
        _FakeGlobalSearchRepository(
          result: const GlobalSearchResult(sourcesQueried: 12),
        ),
      );

      await _search(tester, 'nonexistent title');

      expect(find.text('No results found'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('repository error shows error state with retry', (tester) async {
      await _pumpSearch(
        tester,
        _FakeGlobalSearchRepository(
          error: const NetworkError(message: 'offline'),
        ),
      );

      await _search(tester, 'one piece');

      expect(find.text('Search failed'), findsOneWidget);
      expect(find.text('TRY AGAIN'), findsOneWidget);
      expect(find.byType(CircularProgressIndicator), findsNothing);
    });

    testWidgets('tapping a source result navigates to source detail',
        (tester) async {
      await _pumpSearch(
        tester,
        _FakeGlobalSearchRepository(
          result: const GlobalSearchResult(
            items: [
              GlobalSearchItem(
                kind: 'source',
                source: 'mangadex',
                seriesId: 'md-1',
                title: 'One Piece (MangaDex)',
              ),
            ],
            sourcesQueried: 1,
          ),
        ),
      );

      await _search(tester, 'one piece');

      await tester.tap(find.text('One Piece (MangaDex)'));
      await tester.pumpAndSettle();

      expect(find.text('SOURCE mangadex md-1'), findsOneWidget);
    });
  });
}
