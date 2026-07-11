import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/core/error/app_error.dart';
import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/library/models/dashboard_data.dart';
import 'package:manhwamaniacs/shared/providers/repository_providers.dart';

final dashboardProvider = FutureProvider.autoDispose<DashboardData>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);

  final recentlyUpdatedResult = await repo.recentlyUpdated(limit: 8);
  final continueReadingResult = await repo.continueReading(limit: 6);
  final statisticsResult = await repo.statistics();

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
