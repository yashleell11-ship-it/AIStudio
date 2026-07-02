import 'package:aistudio_mobile/features/library/models/library_list_state.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/features/library/utils/library_preferences.dart';
import 'package:aistudio_mobile/shared/providers/core_providers.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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

final searchQueryProvider = StateProvider<LibraryQuery>(
  (ref) => const LibraryQuery(viewMode: LibraryViewMode.list),
  name: 'searchQuery',
);

final libraryListProvider =
    AsyncNotifierProvider.autoDispose<LibraryListNotifier, LibraryListState>(
  LibraryListNotifier.new,
  name: 'libraryList',
);

final searchListProvider =
    AsyncNotifierProvider.autoDispose<SearchListNotifier, LibraryListState>(
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

  Future<LibraryListState> _fetchFirstPage(LibraryQuery query) async {
    final page = await _fetchPage(query, 1);
    return LibraryListState(
      items: page.items,
      total: page.total,
      page: 1,
      hasNext: page.hasNext,
    );
  }

  Future<({List<SeriesSummary> items, int total, bool hasNext})> _fetchPage(
    LibraryQuery query,
    int page,
  ) =>
      fetchLibraryListPage(ref, query, page);
}

class SearchListNotifier extends AutoDisposeAsyncNotifier<LibraryListState> {
  @override
  Future<LibraryListState> build() async {
    final query = ref.watch(searchQueryProvider);
    if (!query.isSearching) {
      return const LibraryListState(items: [], total: 0, page: 1, hasNext: false);
    }
    return _fetchFirstPage(query);
  }

  Future<void> refresh() async {
    final query = ref.read(searchQueryProvider);
    if (!query.isSearching) {
      state = const AsyncData(
        LibraryListState(items: [], total: 0, page: 1, hasNext: false),
      );
      return;
    }
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => _fetchFirstPage(query));
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || !current.hasNext || current.isLoadingMore) return;

    final query = ref.read(searchQueryProvider);
    state = AsyncData(current.copyWith(isLoadingMore: true, clearError: true));

    final nextPage = current.page + 1;
    final result = await fetchLibraryListPage(ref, query, nextPage);

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

    state = AsyncData(
      current.copyWith(
        items: applySearchClientFilters(updatedItems, ref.read(searchQueryProvider)),
        clearError: true,
      ),
    );
  }

  Future<LibraryListState> _fetchFirstPage(LibraryQuery query) async {
    final page = await fetchLibraryListPage(ref, query, 1);
    return LibraryListState(
      items: page.items,
      total: page.total,
      page: 1,
      hasNext: page.hasNext,
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
