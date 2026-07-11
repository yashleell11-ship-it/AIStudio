import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';

void main() {
  group('LibraryStatistics.fromJson', () {
    test('parses dashboard stat fields from API response', () {
      final stats = LibraryStatistics.fromJson({
        'total_series': 42,
        'total_chapters': 1240,
        'total_pages': 18500,
        'completed_series': 10,
        'in_progress': 8,
        'favorites': 5,
        'completion_rate_pct': 23.8,
        'total_reading_time_estimate_minutes': 3600,
        'pages_read_this_week': 120,
        'reading_streak_days': 3,
        'reading_velocity_pages_per_hour': 45.5,
      });

      expect(stats.totalSeries, 42);
      expect(stats.totalChapters, 1240);
      expect(stats.totalPages, 18500);
      expect(stats.readingStreakDays, 3);
    });
  });
}
