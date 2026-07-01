import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';

/// Library statistics shown on the dashboard.
///
/// Derived from existing [LibraryRepository] methods because the statistics
/// endpoint is not yet exposed on the repository interface.
class DashboardStats {
  const DashboardStats({
    required this.totalSeries,
    required this.totalChapters,
    required this.totalPages,
    required this.readingStreakDays,
  });

  final int totalSeries;
  final int totalChapters;
  final int totalPages;
  final int readingStreakDays;

  factory DashboardStats.fromLibraryData({
    required int totalSeries,
    required List<SeriesSummary> seriesSample,
    required List<ContinueReadingItem> continueReading,
  }) {
    return DashboardStats(
      totalSeries: totalSeries,
      totalChapters: seriesSample.fold<int>(
        0,
        (sum, series) => sum + series.totalChapters,
      ),
      totalPages: seriesSample.fold<int>(
        0,
        (sum, series) => sum + series.totalPages,
      ),
      readingStreakDays: _computeReadingStreak(continueReading),
    );
  }
}

int _computeReadingStreak(List<ContinueReadingItem> items) {
  if (items.isEmpty) return 0;

  final readDates = items
      .map(
        (item) => DateTime(
          item.lastReadAt.year,
          item.lastReadAt.month,
          item.lastReadAt.day,
        ),
      )
      .toSet();

  var streak = 0;
  var cursor = DateTime.now();
  cursor = DateTime(cursor.year, cursor.month, cursor.day);

  if (!readDates.contains(cursor)) {
    cursor = cursor.subtract(const Duration(days: 1));
  }

  while (readDates.contains(cursor)) {
    streak++;
    cursor = cursor.subtract(const Duration(days: 1));
  }

  return streak;
}
