import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/library_list_state.dart';
import 'package:aistudio_mobile/features/library/models/library_query.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

const _listPageSize = 20;
const _searchPageSize = 40;

final libraryQueryProvider = StateProvider<LibraryQuery>(
  (ref) => const LibraryQuery(),
  name: 'libraryQuery',
);

final libraryListProvider =
    AsyncNotifierProvider.autoDispose<LibraryListNotifier, LibraryListState>(
  LibraryListNotifier.new,
  name: 'libraryList',
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
        total: query.isSearching
            ? current.items.length + result.items.length
            : result.total,
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
  ) async {
    final repo = ref.read(libraryRepositoryProvider);

    if (query.isSearching) {
      final result = await repo.search(query.search.trim(), page: page);
      if (result.isErr) throw result.error;
      final items = result.value;
      return (
        items: items,
        total: items.length,
        hasNext: items.length >= _searchPageSize,
      );
    }

    final result = await repo.listSeries(
      page: page,
      perPage: _listPageSize,
      sort: query.sortParam,
      status: query.statusParam,
      isFavorite: query.favoritesOnly ? true : null,
    );
    if (result.isErr) throw result.error;

    final paged = result.value;
    return (
      items: paged.items,
      total: paged.total,
      hasNext: paged.hasNext,
    );
  }
}
