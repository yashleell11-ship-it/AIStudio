import 'package:aistudio_mobile/features/library/models/series_summary.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final json = {
    'id': 1,
    'library_id': 1,
    'title': 'Solo Leveling',
    'sort_title': 'solo leveling',
    'original_title': null,
    'author': 'Chugong',
    'artist': null,
    'description': 'A hunter awakens.',
    'status': 'completed',
    'content_rating': 'teen',
    'language': 'ko',
    'year': 2018,
    'cover_path': '/covers/1.jpg',
    'folder_path': '/library/solo-leveling',
    'is_favorite': true,
    'reading_status': 'reading',
    'chapter_count': 179,
    'read_chapters': 50,
    'page_count': 3580,
    'total_chapters': 179,
    'total_pages': 3580,
    'first_chapter_id': 101,
    'created_at': '2024-01-01T00:00:00',
    'updated_at': '2024-06-01T00:00:00',
    'reading_progress': {
      'series_id': 1,
      'chapter_id': 150,
      'last_page': 10,
      'progress_pct': 27.9,
      'last_read_at': '2024-06-01T12:00:00',
    },
  };

  group('SeriesSummary.fromJson', () {
    test('parses all fields', () {
      final s = SeriesSummary.fromJson(json);
      expect(s.id, 1);
      expect(s.title, 'Solo Leveling');
      expect(s.isFavorite, isTrue);
      expect(s.chapterCount, 179);
      expect(s.readingProgress, isNotNull);
      expect(s.readingProgress!.chapterId, 150);
    });

    test('computes readProgressPct', () {
      final s = SeriesSummary.fromJson(json);
      expect(s.readProgressPct, closeTo(50 / 179, 0.001));
    });

    test('handles null reading_progress', () {
      final noProgress = Map<String, dynamic>.from(json);
      noProgress['reading_progress'] = null;
      final s = SeriesSummary.fromJson(noProgress);
      expect(s.readingProgress, isNull);
    });
  });
}
