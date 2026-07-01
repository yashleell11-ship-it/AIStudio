import 'package:aistudio_mobile/core/error/app_error.dart';
import 'package:aistudio_mobile/core/utils/result.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_data.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_stats.dart';
import 'package:aistudio_mobile/shared/providers/repository_providers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final dashboardProvider = FutureProvider.autoDispose<DashboardData>((ref) async {
  final repo = ref.watch(libraryRepositoryProvider);

  final recentlyUpdatedResult = await repo.recentlyUpdated(limit: 8);
  final continueReadingResult = await repo.continueReading(limit: 6);
  final seriesResult = await repo.listSeries(page: 1, perPage: 100);

  final error = _firstError([
    recentlyUpdatedResult,
    continueReadingResult,
    seriesResult,
  ]);
  if (error != null) throw error;

  final recentlyUpdated = recentlyUpdatedResult.value;
  final continueReading = continueReadingResult.value;
  final seriesPage = seriesResult.value;

  return DashboardData(
    recentlyUpdated: recentlyUpdated,
    continueReading: continueReading,
    stats: DashboardStats.fromLibraryData(
      totalSeries: seriesPage.total,
      seriesSample: seriesPage.items,
      continueReading: continueReading,
    ),
  );
});

AppError? _firstError(List<Result<dynamic>> results) {
  for (final result in results) {
    if (result.isErr) return result.error;
  }
  return null;
}
