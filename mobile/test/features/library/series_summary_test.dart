import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/models/followed_series.dart';

void main() {
  final json = {
    'id': 1,
    'source_id': 'asurascans',
    'series_key': 'solo-leveling',
    'title': 'Solo Leveling',
    'cover_url': '/sources/asurascans/series/solo-leveling/cover',
    'is_favorite': true,
    'reading_status': 'reading',
    'notify': true,
    'sort_order': 0,
    'content_rating': 'teen',
    'rating': 'safe',
    'mature_override': null,
    'known_chapters': [
      {'key': '1', 'number': 1.0, 'title': 'Chapter 1', 'published_at': null},
      {'key': '2', 'number': 2.0, 'title': 'Chapter 2', 'published_at': null},
    ],
    'chapter_count': 179,
    'last_checked_at': '2024-06-01T12:00:00',
    'created_at': '2024-01-01T00:00:00',
    'updated_at': '2024-06-01T00:00:00',
  };

  group('FollowedSeries.fromJson', () {
    test('parses all fields', () {
      final s = FollowedSeries.fromJson(json);
      expect(s.id, 1);
      expect(s.sourceId, 'asurascans');
      expect(s.seriesKey, 'solo-leveling');
      expect(s.title, 'Solo Leveling');
      expect(s.isFavorite, isTrue);
      expect(s.notify, isTrue);
      expect(s.chapterCount, 179);
      expect(s.knownChapters, hasLength(2));
      expect(s.knownChapters.first.key, '1');
    });

    test('copyWith flips favorite/status/notify without touching identity', () {
      final s = FollowedSeries.fromJson(json);
      final updated = s.copyWith(isFavorite: false, readingStatus: 'completed');

      expect(updated.isFavorite, isFalse);
      expect(updated.readingStatus, 'completed');
      expect(updated.id, s.id);
      expect(updated.sourceId, s.sourceId);
      expect(updated.seriesKey, s.seriesKey);
    });

    test('handles a missing/empty cover_url', () {
      final noCover = Map<String, dynamic>.from(json)..remove('cover_url');
      final s = FollowedSeries.fromJson(noCover);
      expect(s.coverUrl, isEmpty);
    });
  });
}
