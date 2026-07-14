import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/library/models/global_search_result.dart';
import 'package:manhwamaniacs/features/library/models/library_list_state.dart';
import 'package:manhwamaniacs/features/library/models/library_query.dart';
import 'package:manhwamaniacs/features/library/models/series_summary.dart';
import 'package:manhwamaniacs/features/library/utils/library_preferences.dart';
import 'package:manhwamaniacs/shared/providers/core_providers.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

const _listPageSize = 20;
const _searchPageSize = 40;

final libraryQueryProvider =
    NotifierProvider<LibraryQueryNotifier, LibraryQuery>(
  LibraryQueryNotifier.new,
  name: 'libraryQuery',
);

class LibraryQueryNotifier extends Notifier<LibraryQuery> {
  @override
  LibraryQuery build() => _normalizeBrowseQuery(readLibraryQuery(ref.read(sharedPrefsProvider)));

  void updateQuery(LibraryQuery query) {
    final normalized = _normalizeBrowseQuery(query);
    final shouldPersist = libraryQueryPersistedFieldsChanged(state, normalized);
    state = normalized;
    if (shouldPersist) {
      writeLibraryQuery(ref.read(sharedPrefsProvider), state);
    }
  }

  void patchQuery(LibraryQuery Function(LibraryQuery current) update) {
    updateQuery(update(state));
  }
}

LibraryQuery _normalizeBrowseQuery(LibraryQuery query) {
  if (!libraryBrowseSortOptions.contains(query.sort)) {
    return query.copyWith(sort: LibrarySort.recent);
  }
  return query;
}

/// The raw federated-search query text. Empty means "not searching".
final searchQueryProvider = StateProvider<String>(
  (ref) => '',
  name: 'searchQuery',
);

/// Grid/list toggle for the search results (federated search has no server
/// sort/filter, so this is the only presentation control it carries).
final searchViewModeProvider = StateProvider<LibraryViewMode>(
  (ref) => LibraryViewMode.list,
  name: 'searchViewMode',
);

final libraryListProvider =
    AsyncNotifierProvider.autoDispose<LibraryListNotifier, LibraryListState>(
  LibraryListNotifier.new,
  name: 'libraryList',
);

/// Federated search results (local library + every enabled remote source),
/// keyed off [searchQueryProvider]. Always resolves to data or error — never
/// an indefinite loading state.
final searchListProvider = AsyncNotifierProvider.autoDispose<SearchListNotifier,
    GlobalSearchResult>(
  SearchListNotifier.new,
  name: 'searchList',
);

class LibraryListNotifier extends AutoDisposeAsyncNotifier<LibraryListState> {
  @override
  Future<LibraryListState> build() async {
    final query = ref.watch(libraryQueryProvider);
    return _fetchFirstPage(query);
  }

  Future<void> refresh() async {
    final query = ref.read(libraryQueryProvider);
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => _fetchFirstPage(query));
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || !current.hasNext || current.isLoadingMore) return;

    final query = ref.read(libraryQueryProvider);
    state = AsyncData(current.copyWith(isLoadingMore: true, clearError: true));

    final nextPage = current.page + 1;
    final result = await _fetchPage(query, nextPage);

    state = AsyncData(
      current.copyWith(
        items: [...current.items, ...result.items],
        page: nextPage,
        hasNext: result.hasNext,
        total: query.usesListSeriesFetch
            ? result.total
            : current.items.length + result.items.length,
        isLoadingMore: false,
      ),
    );
  }

  Future<void> toggleFavorite(int seriesId) async {
    final current = state.valueOrNull;
    if (current == null) return;

    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.toggleFavorite(seriesId);
    if (result.isErr) {
      state = AsyncData(current.copyWith(error: result.error));
      return;
    }

    final updatedItems = current.items.map((series) {
      if (series.id != seriesId) return series;
      return series.copyWith(isFavorite: !series.isFavorite);
    }).toList();

    state = AsyncData(current.copyWith(items: updatedItems, clearError: true));
  }

  /// Batch favorite/unfavorite a multi-selected set of series. Only calls
  /// the API for items whose current state actually needs to change (so
  /// "Favorite selected" on an already-mixed selection doesn't needlessly
  /// re-toggle series that are already favorited), and only flips items in
  /// local state whose API call actually succeeded.
  Future<void> batchSetFavorite(Set<int> seriesIds, {required bool favorite}) async {
    final current = state.valueOrNull;
    if (current == null) return;

    final targets = current.items
        .where((series) => seriesIds.contains(series.id) && series.isFavorite != favorite)
        .toList();
    if (targets.isEmpty) return;

    final repo = ref.read(libraryRepositoryProvider);
    final results = await Future.wait(targets.map((series) => repo.toggleFavorite(series.id)));

    final succeededIds = <int>{
      for (var i = 0; i < targets.length; i++)
        if (results[i].isOk) targets[i].id,
    };
    if (succeededIds.isEmpty) return;

    final updatedItems = current.items.map((series) {
      if (!succeededIds.contains(series.id)) return series;
      return series.copyWith(isFavorite: favorite);
    }).toList();

    state = AsyncData(current.copyWith(items: updatedItems, clearError: true));
  }

  Future<LibraryListState> _fetchFirstPage(LibraryQuery query) async {
    final page = await _fetchPage(query, 1);
    return LibraryListState(
      items: page.items,
      total: page.total,
      hasNext: page.hasNext,
    );
  }

  Future<({List<SeriesSummary> items, int total, bool hasNext})> _fetchPage(
    LibraryQuery query,
    int page,
  ) =>
      fetchLibraryListPage(ref, query, page);
}

/// Drives federated search via [GlobalSearchRepository].
///
/// Loading always resolves: `build` returns an empty result for a blank query
/// and otherwise returns data or throws (→ AsyncError). Staleness is handled on
/// two fronts — Riverpod re-runs `build` whenever [searchQueryProvider] changes
/// and only the latest build's future is applied to state (so a slow response
/// for an old query is discarded), and an explicit request token guards the
/// imperative `loadMore`/`refresh` paths. The UI additionally debounces
/// keystrokes before mutating [searchQueryProvider].
class SearchListNotifier
    extends AutoDisposeAsyncNotifier<GlobalSearchResult> {
  var _requestId = 0;

  @override
  Future<GlobalSearchResult> build() async {
    final query = ref.watch(searchQueryProvider).trim();
    if (query.isEmpty) {
      return const GlobalSearchResult();
    }
    final requestId = ++_requestId;
    final result =
        await ref.read(globalSearchRepositoryProvider).search(query);
    // Guard against a superseded query resolving late.
    if (requestId != _requestId) {
      return state.valueOrNull ?? const GlobalSearchResult();
    }
    if (result.isErr) throw result.error;
    return result.value;
  }

  Future<void> refresh() async {
    ref.invalidateSelf();
    await future;
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || !current.hasMore || current.isLoadingMore) return;

    final query = ref.read(searchQueryProvider).trim();
    if (query.isEmpty) return;

    final requestId = ++_requestId;
    state = AsyncData(current.copyWith(isLoadingMore: true));

    final nextPage = current.page + 1;
    final result = await ref
        .read(globalSearchRepositoryProvider)
        .search(query, page: nextPage);

    // Ignore if a newer query/refresh superseded this page request.
    if (requestId != _requestId) return;

    final latest = state.valueOrNull ?? current;
    if (result.isErr) {
      // Keep the results we already have; just stop the load-more spinner.
      state = AsyncData(latest.copyWith(isLoadingMore: false));
      return;
    }

    final next = result.value;
    state = AsyncData(
      latest.copyWith(
        items: [...latest.items, ...next.items],
        page: nextPage,
        hasMore: next.hasMore,
        sourcesQueried: next.sourcesQueried,
        sourcesFailed: next.sourcesFailed,
        isLoadingMore: false,
      ),
    );
  }
}

Future<({List<SeriesSummary> items, int total, bool hasNext})> fetchLibraryListPage(
  Ref ref,
  LibraryQuery query,
  int page,
) async {
  final repo = ref.read(libraryRepositoryProvider);

  if (!query.usesListSeriesFetch) {
    final result = await repo.search(query.search.trim(), page: page);
    if (result.isErr) throw result.error;
    final filtered = applySearchClientFilters(result.value, query);
    return (
      items: filtered,
      total: filtered.length,
      hasNext: result.value.length >= _searchPageSize,
    );
  }

  final perPage = query.isSearching ? _searchPageSize : _listPageSize;
  final result = await repo.listSeries(
    page: page,
    perPage: perPage,
    sort: query.sortParam,
    search: query.isSearching ? query.search.trim() : null,
    readingStatus: query.readingStatusParam,
    hasChapters: query.hasChaptersParam,
    isFavorite: query.favoritesOnly ? true : null,
  );
  if (result.isErr) throw result.error;

  final paged = result.value;
  final items = applyLibraryClientFilters(paged.items, query, sortResults: false);
  return (
    items: items,
    total: paged.total,
    hasNext: paged.hasNext,
  );
}

List<SeriesSummary> applySearchClientFilters(
  List<SeriesSummary> items,
  LibraryQuery query,
) =>
    applyLibraryClientFilters(items, query, sortResults: true);

List<SeriesSummary> applyLibraryClientFilters(
  List<SeriesSummary> items,
  LibraryQuery query, {
  required bool sortResults,
}) {
  var filtered = items;

  if (query.favoritesOnly) {
    filtered = filtered.where((series) => series.isFavorite).toList();
  }

  filtered = switch (query.filter) {
    LibraryFilter.all => filtered,
    LibraryFilter.downloaded => filtered,
    LibraryFilter.reading =>
      filtered.where((series) => series.readingStatus == 'reading').toList(),
    LibraryFilter.completed =>
      filtered.where((series) => series.readingStatus == 'completed').toList(),
  };

  filtered = List<SeriesSummary>.from(filtered);
  if (sortResults) {
    filtered.sort((a, b) => _compareSeries(a, b, query.sort));
  }
  return filtered;
}

int _compareSeries(SeriesSummary a, SeriesSummary b, LibrarySort sort) {
  return switch (sort) {
    LibrarySort.title => a.title.toLowerCase().compareTo(b.title.toLowerCase()),
    LibrarySort.author => (a.author ?? '')
        .toLowerCase()
        .compareTo((b.author ?? '').toLowerCase()),
    LibrarySort.year => (b.year ?? 0).compareTo(a.year ?? 0),
    LibrarySort.totalChapters =>
      b.chapterCount.compareTo(a.chapterCount),
    LibrarySort.dateAdded => b.createdAt.compareTo(a.createdAt),
    LibrarySort.recent =>
      (b.readingProgress?.lastReadAt ?? DateTime.fromMillisecondsSinceEpoch(0))
          .compareTo(
        a.readingProgress?.lastReadAt ?? DateTime.fromMillisecondsSinceEpoch(0),
      ),
    LibrarySort.updated => b.updatedAt.compareTo(a.updatedAt),
  };
}
