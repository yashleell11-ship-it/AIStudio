import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/collections/providers/collections_provider.dart';
import 'package:aistudio_mobile/features/library/models/collection_detail.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final collectionDetailProvider = AsyncNotifierProvider.autoDispose
    .family<CollectionDetailNotifier, CollectionDetail, int>(
  CollectionDetailNotifier.new,
  name: 'collectionDetail',
);

class CollectionDetailNotifier
    extends AutoDisposeFamilyAsyncNotifier<CollectionDetail, int> {
  @override
  Future<CollectionDetail> build(int collectionId) async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.getCollection(collectionId);
    if (result.isErr) throw result.error;
    return result.value;
  }

  Future<void> refresh() async {
    final collectionId = arg;
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final repo = ref.read(libraryRepositoryProvider);
      final result = await repo.getCollection(collectionId);
      if (result.isErr) throw result.error;
      return result.value;
    });
  }

  Future<AppError?> updateCollection({
    String? name,
    String? description,
  }) async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.updateCollection(
      arg,
      name: name,
      description: description,
    );
    if (result.isErr) return result.error;
    await refresh();
    ref.invalidate(collectionsProvider);
    return null;
  }

  Future<AppError?> deleteCollection() async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.deleteCollection(arg);
    if (result.isErr) return result.error;
    ref.invalidate(collectionsProvider);
    return null;
  }

  Future<AppError?> addSeries(int seriesId) async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.addSeriesToCollection(arg, seriesId);
    if (result.isErr) return result.error;
    await refresh();
    ref.invalidate(collectionsProvider);
    return null;
  }

  Future<AppError?> removeSeries(int seriesId) async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.removeSeriesFromCollection(arg, seriesId);
    if (result.isErr) return result.error;
    await refresh();
    ref.invalidate(collectionsProvider);
    return null;
  }
}

final librarySeriesPickerProvider =
    FutureProvider.autoDispose<List<SeriesSummary>>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.listSeries(page: 1, perPage: 200);
  if (result.isErr) throw result.error;
  return result.value.items;
});
