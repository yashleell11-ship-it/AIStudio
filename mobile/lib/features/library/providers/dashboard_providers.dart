import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/dashboard_data.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final dashboardProvider = FutureProvider.autoDispose<DashboardData>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);

  // Started together, awaited after: the home screen cannot draw until all
  // three have landed, and statistics is the heaviest endpoint in the app
  // (`GET /library/statistics` scans the profile's whole session history), so
  // running it third in a chain put its cost in front of first paint for no
  // reason. Every request is independent and none feeds another.
  final recentlyUpdated = repo.recentlyUpdated(limit: 8);
  final continueReading = repo.continueReading(limit: 6);
  final statistics = repo.statistics();

  final recentlyUpdatedResult = await recentlyUpdated;
  final continueReadingResult = await continueReading;
  final statisticsResult = await statistics;

  final error = _firstError([
    recentlyUpdatedResult,
    continueReadingResult,
    statisticsResult,
  ]);
  if (error != null) throw error;

  return DashboardData(
    recentlyUpdated: recentlyUpdatedResult.value,
    continueReading: continueReadingResult.value,
    stats: statisticsResult.value,
  );
});

AppError? _firstError(List<Result<dynamic>> results) {
  for (final result in results) {
    if (result.isErr) return result.error;
  }
  return null;
}
