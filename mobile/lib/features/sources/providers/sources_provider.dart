import 'package:aistudio_mobile/core/utils/pagination.dart';
import 'package:aistudio_mobile/features/sources/models/source.dart';
import 'package:aistudio_mobile/features/sources/models/source_series.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final sourcesListProvider = FutureProvider.autoDispose<List<SourceSummary>>((ref) async {
  final repo = ref.watch(sourcesRepositoryProvider);
  final result = await repo.listSources();
  if (result.isErr) throw result.error;
  return result.value;
});

class SourceBrowseQuery {
  const SourceBrowseQuery({
    required this.sourceId,
    this.page = 1,
    this.search = '',
    this.sort = 'default',
  });

  final String sourceId;
  final int page;
  final String search;
  final String sort;

  SourceBrowseQuery copyWith({
    int? page,
    String? search,
    String? sort,
  }) =>
      SourceBrowseQuery(
        sourceId: sourceId,
        page: page ?? this.page,
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

final sourceBrowseProvider =
    FutureProvider.autoDispose.family<PagedResult<SourceSeriesSummary>, String>(
  (ref, sourceId) async {
    final query = ref.watch(sourceBrowseQueryProvider(sourceId));
    final repo = ref.watch(sourcesRepositoryProvider);
    final result = await repo.listSeries(
      sourceId,
      page: query.page,
      query: query.search.isEmpty ? null : query.search,
      sort: query.sort == 'default' ? null : query.sort,
    );
    if (result.isErr) throw result.error;
    return result.value;
  },
);

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
