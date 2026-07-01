import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/features/library/models/collection.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final collectionSearchProvider = StateProvider<String>(
  (ref) => '',
  name: 'collectionSearch',
);

final collectionsProvider =
    AsyncNotifierProvider.autoDispose<CollectionsNotifier, List<Collection>>(
  CollectionsNotifier.new,
  name: 'collections',
);

class CollectionsNotifier extends AutoDisposeAsyncNotifier<List<Collection>> {
  @override
  Future<List<Collection>> build() async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.listCollections();
    if (result.isErr) throw result.error;
    return result.value;
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() async {
      final repo = ref.read(libraryRepositoryProvider);
      final result = await repo.listCollections();
      if (result.isErr) throw result.error;
      return result.value;
    });
  }

  Future<AppError?> createCollection({
    required String name,
    String? description,
  }) async {
    final repo = ref.read(libraryRepositoryProvider);
    final result = await repo.createCollection(name: name, description: description);
    if (result.isErr) return result.error;
    await refresh();
    return null;
  }
}
