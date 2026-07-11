import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/features/sources/providers/sources_provider.dart';
import 'package:manhwamaniacs/features/sources/repositories/sources_repository.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

SourceSeriesSummary _series(String id, {String title = 'Series'}) {
  return SourceSeriesSummary(
    id: id,
    sourceId: 'test-source',
    title: title,
    chapterCount: 10,
    genres: const [],
    coverUrl: 'https://example.com/$id.jpg',
  );
}

class _FakeSourcesRepository implements SourcesRepository {
  _FakeSourcesRepository(this.pagesByQuery);

  /// Keyed by "query|sort|page" so tests can assert exactly which page was
  /// requested for a given search/sort combination.
  final Map<String, Result<PagedResult<SourceSeriesSummary>>> pagesByQuery;
  final List<int> requestedPages = [];

  @override
  Future<Result<PagedResult<SourceSeriesSummary>>> listSeries(
    String sourceId, {
    int page = 1,
    String? query,
    String? sort,
  }) async {
    requestedPages.add(page);
    final key = '${query ?? ''}|${sort ?? ''}|$page';
    return pagesByQuery[key] ??
        const Ok(PagedResult(items: [], total: 0, page: 1, perPage: 20, hasNext: false));
  }

  @override
  Future<Result<List<SourceBrowseMode>>> listBrowseModes(String sourceId) async =>
      const Ok([]);

  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('build() fetches page 1 and exposes hasNext/total', () async {
    final repo = _FakeSourcesRepository({
      '||1': Ok(
        PagedResult(
          items: [_series('a'), _series('b')],
          total: 50,
          page: 1,
          perPage: 2,
          hasNext: true,
        ),
      ),
    });
    final container = ProviderContainer(
      overrides: [sourcesRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    final state = await container.read(sourceBrowseProvider('test-source').future);

    expect(state.items.map((s) => s.id), ['a', 'b']);
    expect(state.total, 50);
    expect(state.hasNext, isTrue);
    expect(state.page, 1);
  });

  test('loadMore appends the next page instead of replacing it', () async {
    final repo = _FakeSourcesRepository({
      '||1': Ok(
        PagedResult(items: [_series('a')], total: 3, page: 1, perPage: 1, hasNext: true),
      ),
      '||2': Ok(
        PagedResult(items: [_series('b')], total: 3, page: 2, perPage: 1, hasNext: true),
      ),
    });
    final container = ProviderContainer(
      overrides: [sourcesRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    await container.read(sourceBrowseProvider('test-source').future);
    await container.read(sourceBrowseProvider('test-source').notifier).loadMore();

    final state = container.read(sourceBrowseProvider('test-source')).value!;
    expect(state.items.map((s) => s.id), ['a', 'b']);
    expect(state.page, 2);
  });

  test('loadMore is a no-op once hasNext is false', () async {
    final repo = _FakeSourcesRepository({
      '||1': Ok(
        PagedResult(items: [_series('a')], total: 1, page: 1, perPage: 1, hasNext: false),
      ),
    });
    final container = ProviderContainer(
      overrides: [sourcesRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    await container.read(sourceBrowseProvider('test-source').future);
    await container.read(sourceBrowseProvider('test-source').notifier).loadMore();

    // Only the initial page-1 fetch happened -- loadMore made no request.
    expect(repo.requestedPages, [1]);
  });

  test('loadMore leaves existing items in place if the next page fails',
      () async {
    final repo = _FakeSourcesRepository({
      '||1': Ok(
        PagedResult(items: [_series('a')], total: 2, page: 1, perPage: 1, hasNext: true),
      ),
      '||2': const Err(NetworkError(message: 'offline')),
    });
    final container = ProviderContainer(
      overrides: [sourcesRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    await container.read(sourceBrowseProvider('test-source').future);
    await container.read(sourceBrowseProvider('test-source').notifier).loadMore();

    final state = container.read(sourceBrowseProvider('test-source')).value!;
    expect(state.items.map((s) => s.id), ['a']);
    expect(state.isLoadingMore, isFalse);
  });

  test('changing the query resets pagination back to page 1', () async {
    final repo = _FakeSourcesRepository({
      '||1': Ok(
        PagedResult(items: [_series('a')], total: 1, page: 1, perPage: 1, hasNext: false),
      ),
      'solo||1': Ok(
        PagedResult(items: [_series('b', title: 'Solo Leveling')], total: 1, page: 1, perPage: 1, hasNext: false),
      ),
    });
    final container = ProviderContainer(
      overrides: [sourcesRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    await container.read(sourceBrowseProvider('test-source').future);

    container.read(sourceBrowseQueryProvider('test-source').notifier).state =
        container.read(sourceBrowseQueryProvider('test-source')).copyWith(search: 'solo');

    final state = await container.read(sourceBrowseProvider('test-source').future);
    expect(state.items.single.title, 'Solo Leveling');
    expect(state.page, 1);
  });
}
