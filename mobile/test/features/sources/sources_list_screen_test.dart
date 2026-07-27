import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_pin.dart';
import 'package:manhwamaniacs/features/sources/models/source_search_group.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/features/sources/screens/sources_list_screen.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../support/test_overrides.dart';

/// Source ids here are deliberately ones with no known favicon so [SourceLogo]
/// renders its letter avatar instead of reaching for the network in a test.
const _sources = [
  SourceSummary(
    id: 'demonicscans',
    name: 'Demonic Scans',
    description: 'Scanlation group',
    browsable: true,
    supportsImport: true,
  ),
  SourceSummary(
    id: 'aurorascans',
    name: 'Aurora Scans',
    description: 'Scanlation group',
    browsable: true,
    supportsImport: true,
  ),
  SourceSummary(
    id: 'beehentai',
    name: 'Bee Hentai',
    description: 'Adult connector',
    browsable: true,
    supportsImport: false,
    mature: true,
  ),
];

class _FakeSourcesRepository implements SourcesRepository {
  _FakeSourcesRepository({this.pins = const []});

  List<SourcePin> pins;
  List<String>? lastReplacedPins;

  @override
  Future<Result<List<SourceSummary>>> listSources() async => const Ok(_sources);

  @override
  Future<Result<List<SourcePin>>> listPins() async => Ok(pins);

  @override
  Future<Result<List<SourcePin>>> replacePins(List<String> sourceIds) async {
    lastReplacedPins = sourceIds;
    pins = [
      for (var i = 0; i < sourceIds.length; i++)
        SourcePin(sourceId: sourceIds[i], sortOrder: i, name: sourceIds[i]),
    ];
    return Ok(pins);
  }

  @override
  Future<Result<GroupedSearchResult>> searchGrouped(
    String query, {
    int page = 1,
    int perPage = 40,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) =>
      throw UnimplementedError();

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) =>
      throw UnimplementedError();

  @override
  Future<Result<SourceSeriesSummary>> getSeries(
    String sourceId,
    String seriesId,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<List<SourceChapterSummary>>> getChapters(
    String sourceId,
    String seriesId,
  ) =>
      throw UnimplementedError();

  @override
  Future<Result<ReaderChapter>> getReaderChapter(
    String sourceId,
    String seriesId,
    String chapterId,
  ) =>
      throw UnimplementedError();
}

Future<void> _pumpSources(WidgetTester tester, _FakeSourcesRepository repo) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();

  final router = GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, __) => const SourcesListScreen()),
      GoRoute(
        path: '/sources/:sourceId',
        builder: (_, state) =>
            Scaffold(body: Text('BROWSE ${state.pathParameters['sourceId']}')),
      ),
    ],
  );

  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        sourcesRepositoryProvider.overrideWithValue(repo),
        // Pins are scoped to (account, profile) and are only fetched for a
        // signed-in session, so both gates have to be open here.
        authenticatedAuthOverride(),
        activeProfileOverride(),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('SourcesListScreen', () {
    testWidgets('lists every source as a row under "All sources"',
        (tester) async {
      await _pumpSources(tester, _FakeSourcesRepository());

      // Twice: the hero heading, and the section header — which reads
      // "Sources" rather than "All sources" while nothing is pinned.
      expect(find.text('SOURCES'), findsNWidgets(2));
      expect(find.text('Demonic Scans'), findsOneWidget);
      expect(find.text('Aurora Scans'), findsOneWidget);
      expect(find.text('Bee Hentai'), findsOneWidget);
      // Mature connectors are badged rather than hidden.
      expect(find.text('18+'), findsWidgets);
    });

    testWidgets('filter field narrows the list to matching names',
        (tester) async {
      await _pumpSources(tester, _FakeSourcesRepository());

      await tester.enterText(find.byType(TextField), 'aurora');
      await tester.pumpAndSettle();

      expect(find.text('Aurora Scans'), findsOneWidget);
      expect(find.text('Demonic Scans'), findsNothing);
      expect(find.text('Bee Hentai'), findsNothing);
    });

    testWidgets('pinned sources get their own section above the rest',
        (tester) async {
      await _pumpSources(
        tester,
        _FakeSourcesRepository(
          pins: const [
            SourcePin(
              sourceId: 'aurorascans',
              sortOrder: 0,
              name: 'Aurora Scans',
            ),
          ],
        ),
      );

      expect(find.text('PINNED'), findsOneWidget);
      expect(find.text('ALL SOURCES'), findsOneWidget);
      // Once pinned, the source is listed in the Pinned section only.
      expect(find.text('Aurora Scans'), findsOneWidget);
    });

    testWidgets('the Pinned chip scopes the list to pinned sources',
        (tester) async {
      await _pumpSources(
        tester,
        _FakeSourcesRepository(
          pins: const [
            SourcePin(
              sourceId: 'aurorascans',
              sortOrder: 0,
              name: 'Aurora Scans',
            ),
          ],
        ),
      );

      await tester.tap(find.text('Pinned'));
      await tester.pumpAndSettle();

      expect(find.text('Aurora Scans'), findsOneWidget);
      expect(find.text('Demonic Scans'), findsNothing);
    });

    testWidgets('the row pin button writes the whole pinned set back',
        (tester) async {
      final repo = _FakeSourcesRepository();
      await _pumpSources(tester, repo);

      await tester.tap(find.byTooltip('Pin Demonic Scans'));
      await tester.pumpAndSettle();

      expect(repo.lastReplacedPins, ['demonicscans']);
      expect(find.text('PINNED'), findsOneWidget);
    });

    testWidgets('tapping a row opens that source', (tester) async {
      await _pumpSources(tester, _FakeSourcesRepository());

      await tester.tap(find.text('Demonic Scans'));
      await tester.pumpAndSettle();

      expect(find.text('BROWSE demonicscans'), findsOneWidget);
    });
  });
}
