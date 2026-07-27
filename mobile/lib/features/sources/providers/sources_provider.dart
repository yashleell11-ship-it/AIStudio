import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/utils/pagination.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/sources/models/source.dart';
import 'package:manhwamaniacs/features/sources/models/source_series.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final sourcesListProvider = FutureProvider.autoDispose<List<SourceSummary>>((ref) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.listSources();
  if (result.isErr) throw result.error;
  return result.value;
});

/// Free-text filter over the Sources screen. With ~50 connectors this is the
/// primary way to reach one, so it lives in a provider rather than screen state
/// and survives a rebuild of the list.
final sourcesFilterQueryProvider = StateProvider<String>(
  (ref) => '',
  name: 'sourcesFilterQuery',
);

enum SourcesFilter { all, pinned, mature }

final sourcesFilterProvider = StateProvider<SourcesFilter>(
  (ref) => SourcesFilter.all,
  name: 'sourcesFilter',
);

class SourceBrowseQuery {
  const SourceBrowseQuery({
    required this.sourceId,
    this.search = '',
    this.sort = 'default',
  });

  final String sourceId;
  final String search;
  final String sort;

  SourceBrowseQuery copyWith({
    String? search,
    String? sort,
  }) =>
      SourceBrowseQuery(
        sourceId: sourceId,
        search: search ?? this.search,
        sort: sort ?? this.sort,
      );
}

final sourceBrowseQueryProvider = StateProvider.family<SourceBrowseQuery, String>(
  (ref, sourceId) => SourceBrowseQuery(sourceId: sourceId),
  name: 'sourceBrowseQuery',
);

final sourceBrowseModesProvider =
    FutureProvider.autoDispose.family<List<SourceBrowseMode>, String>((ref, sourceId) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.listBrowseModes(sourceId);
  if (result.isErr) throw result.error;
  return result.value;
});

/// Accumulated, infinite-scrollable browse results for one source. Mirrors
/// [LibraryListNotifier]'s accumulate-on-loadMore pattern rather than the
/// page-by-page replace the source browser originally used.
class SourceBrowseState {
  const SourceBrowseState({
    this.items = const [],
    this.total = 0,
    this.page = 1,
    this.hasNext = false,
    this.isLoadingMore = false,
  });

  final List<SourceSeriesSummary> items;
  final int total;
  final int page;
  final bool hasNext;
  final bool isLoadingMore;

  bool get isEmpty => items.isEmpty;

  SourceBrowseState copyWith({
    List<SourceSeriesSummary>? items,
    int? total,
    int? page,
    bool? hasNext,
    bool? isLoadingMore,
  }) =>
      SourceBrowseState(
        items: items ?? this.items,
        total: total ?? this.total,
        page: page ?? this.page,
        hasNext: hasNext ?? this.hasNext,
        isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      );
}

final sourceBrowseProvider = AsyncNotifierProvider.autoDispose
    .family<SourceBrowseNotifier, SourceBrowseState, String>(
  SourceBrowseNotifier.new,
  name: 'sourceBrowse',
);

class SourceBrowseNotifier
    extends AutoDisposeFamilyAsyncNotifier<SourceBrowseState, String> {
  @override
  Future<SourceBrowseState> build(String sourceId) async {
    // Re-fetches from page 1 whenever search/sort changes -- matching
    // LibraryListNotifier/SearchListNotifier, which don't carry a `page`
    // field in their query either; a fresh query always restarts pagination.
    final query = ref.watch(sourceBrowseQueryProvider(sourceId));
    final page = await _fetchPage(sourceId, query, 1);
    return SourceBrowseState(
      items: page.items,
      total: page.total,
      page: page.page,
      hasNext: page.hasNext,
    );
  }

  Future<void> loadMore() async {
    final current = state.valueOrNull;
    if (current == null || !current.hasNext || current.isLoadingMore) return;

    state = AsyncData(current.copyWith(isLoadingMore: true));

    final query = ref.read(sourceBrowseQueryProvider(arg));
    final nextPage = current.page + 1;
    final result = await _fetchPageResult(arg, query, nextPage);

    if (result.isErr) {
      // Leave existing items in place; just stop showing the loading spinner
      // so the user can retry by scrolling again.
      state = AsyncData(current.copyWith(isLoadingMore: false));
      return;
    }

    final page = result.value;
    state = AsyncData(
      current.copyWith(
        items: [...current.items, ...page.items],
        page: page.page,
        hasNext: page.hasNext,
        isLoadingMore: false,
      ),
    );
  }

  Future<void> refresh() async {
    // Keep the previous value attached so the AsyncValue stays *reloading*
    // rather than a fresh load; skipLoadingOnReload then keeps the grid on
    // screen (behind the RefreshIndicator spinner) instead of flashing the
    // full-screen "Opening…" loader.
    state = const AsyncLoading<SourceBrowseState>().copyWithPrevious(state);
    state = await AsyncValue.guard(() => build(arg));
  }

  Future<PagedResult<SourceSeriesSummary>> _fetchPage(
    String sourceId,
    SourceBrowseQuery query,
    int page,
  ) async {
    final result = await _fetchPageResult(sourceId, query, page);
    if (result.isErr) throw result.error;
    return result.value;
  }

  Future<Result<PagedResult<SourceSeriesSummary>>> _fetchPageResult(
    String sourceId,
    SourceBrowseQuery query,
    int page,
  ) {
    final repo = ref.read(sourcesRepositoryProvider);
    return repo.listSeries(
      sourceId,
      page: page,
      query: query.search.isEmpty ? null : query.search,
      sort: query.sort == 'default' ? null : query.sort,
    );
  }
}

class SourceSeriesDetailData {
  const SourceSeriesDetailData({
    required this.series,
    required this.chapters,
  });

  final SourceSeriesSummary series;
  final List<SourceChapterSummary> chapters;
}

final sourceSeriesDetailProvider = FutureProvider.autoDispose
    .family<SourceSeriesDetailData, ({String sourceId, String seriesId})>(
  (ref, params) async {
    final repo = ref.watch(sourcesRepositoryProvider);
    final seriesResult = await repo.getSeries(params.sourceId, params.seriesId);
    final chaptersResult = await repo.getChapters(params.sourceId, params.seriesId);
    if (seriesResult.isErr) throw seriesResult.error;
    if (chaptersResult.isErr) throw chaptersResult.error;
    return SourceSeriesDetailData(
      series: seriesResult.value,
      chapters: chaptersResult.value,
    );
  },
);