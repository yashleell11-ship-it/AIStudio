import 'package:aistudio_mobile/features/library/models/continue_reading_item.dart';
import 'package:aistudio_mobile/features/library/models/dashboard_stats.dart';
import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:flutter_test/flutter_test.dart';

SeriesSummary _series({
  required int id,
  int totalChapters = 10,
  int totalPages = 100,
}) {
  return SeriesSummary(
    id: id,
    libraryId: 1,
    title: 'Series $id',
    sortTitle: 'series $id',
    contentRating: 'teen',
    language: 'en',
    folderPath: '/library/$id',
    isFavorite: false,
    readingStatus: 'unread',
    chapterCount: totalChapters,
    readChapters: 0,
    pageCount: totalPages,
    totalChapters: totalChapters,
    totalPages: totalPages,
    createdAt: DateTime(2024, 1, 1),
    updatedAt: DateTime(2024, 6, 1),
  );
}

ContinueReadingItem _continueItem(DateTime lastReadAt) {
  return ContinueReadingItem(
    seriesId: 1,
    seriesTitle: 'Test',
    chapterId: 1,
    chapterTitle: 'Ch 1',
    lastPage: 1,
    progressPct: 10,
    lastReadAt: lastReadAt,
  );
}

void main() {
  group('DashboardStats.fromLibraryData', () {
    test('aggregates totals from series sample', () {
      final stats = DashboardStats.fromLibraryData(
        totalSeries: 42,
        seriesSample: [
          _series(id: 1, totalChapters: 10, totalPages: 100),
          _series(id: 2, totalChapters: 20, totalPages: 200),
        ],
        continueReading: const [],
      );

      expect(stats.totalSeries, 42);
      expect(stats.totalChapters, 30);
      expect(stats.totalPages, 300);
      expect(stats.readingStreakDays, 0);
    });

    test('computes reading streak from continue reading dates', () {
      final today = DateTime.now();
      final yesterday = today.subtract(const Duration(days: 1));

      final stats = DashboardStats.fromLibraryData(
        totalSeries: 1,
        seriesSample: [_series(id: 1)],
        continueReading: [
          _continueItem(today),
          _continueItem(yesterday),
        ],
      );

      expect(stats.readingStreakDays, 2);
    });
  });
}
