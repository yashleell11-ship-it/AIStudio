import 'package:aistudio_mobile/features/library/models/series_detail.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final seriesDetailProvider =
    FutureProvider.autoDispose.family<SeriesDetail, int>((ref, seriesId) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.getSeries(seriesId);
  if (result.isErr) throw result.error;
  return result.value;
});
