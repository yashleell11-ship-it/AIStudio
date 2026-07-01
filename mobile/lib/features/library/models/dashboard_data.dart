import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_stats.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';

class DashboardData {
  const DashboardData({
    required this.recentlyUpdated,
    required this.continueReading,
    required this.stats,
  });

  final List<SeriesSummary> recentlyUpdated;
  final List<ContinueReadingItem> continueReading;
  final DashboardStats stats;

  bool get isEmpty =>
      stats.totalSeries == 0 &&
      recentlyUpdated.isEmpty &&
      continueReading.isEmpty;
}
