import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/library_statistics.dart';

void main() {
  group('LibraryStatistics.fromJson', () {
    test('parses followed-series stat fields from API response', () {
      final stats = LibraryStatistics.fromJson({
        'followed_total': 42,
        'favorites': 5,
        'by_reading_status': {'reading': 8, 'completed': 10, 'unread': 24},
        'chapters_completed': 1240,
      });

      expect(stats.followedTotal, 42);
      expect(stats.favorites, 5);
      expect(stats.byReadingStatus['completed'], 10);
      expect(stats.chaptersCompleted, 1240);
    });

    test('defaults missing fields to empty/zero', () {
      final stats = LibraryStatistics.fromJson(const {});

      expect(stats.followedTotal, 0);
      expect(stats.favorites, 0);
      expect(stats.byReadingStatus, isEmpty);
      expect(stats.chaptersCompleted, 0);
    });
  });
}
