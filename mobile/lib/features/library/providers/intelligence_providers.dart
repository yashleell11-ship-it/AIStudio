import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';
import 'package:manhwamaniacs/features/library/models/reading_history_item.dart';
import 'package:manhwamaniacs/features/library/models/recommendation.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final statisticsProvider = FutureProvider.autoDispose<LibraryStatistics>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.statistics();
  if (result.isErr) throw result.error;
  return result.value;
});

final recommendationsProvider =
    FutureProvider.autoDispose<List<RecommendationGenre>>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.recommendations(limit: 12);
  if (result.isErr) throw result.error;
  return result.value;
});

final readingHistoryProvider =
    FutureProvider.autoDispose<List<ReadingHistoryItem>>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);
  final result = await repo.readingHistory();
  if (result.isErr) throw result.error;
  return result.value;
});
