import 'package:aistudio_mobile/features/downloads/models/download_item.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final json = {
    'id': 1,
    'source': 'mangakatana',
    'series_id': 'solo-leveling',
    'chapter_id': 'ch-001',
    'series_title': 'Solo Leveling',
    'chapter_title': 'Chapter 1',
    'status': 'downloading',
    'progress': 0.45,
    'pages_done': 9,
    'pages_total': 20,
    'bytes_downloaded': 4096000,
    'speed_bps': 512000.0,
    'speed_mbps': 0.5,
    'eta_seconds': 22.0,
    'local_chapter_id': null,
    'created_at': '2024-01-01T00:00:00',
    'updated_at': '2024-01-01T00:01:00',
    'error': null,
    'priority': 0,
    'queue_state': 'active',
    'retry_count': 0,
  };

  group('DownloadItem.fromJson', () {
    test('parses status flags', () {
      final item = DownloadItem.fromJson(json);
      expect(item.isDownloading, isTrue);
      expect(item.isQueued, isFalse);
      expect(item.isCompleted, isFalse);
    });

    test('parses numeric progress', () {
      final item = DownloadItem.fromJson(json);
      expect(item.progress, closeTo(0.45, 0.001));
      expect(item.speedMbps, closeTo(0.5, 0.001));
    });

    test('completed status flag', () {
      final completed = Map<String, dynamic>.from(json);
      completed['status'] = 'completed';
      final item = DownloadItem.fromJson(completed);
      expect(item.isCompleted, isTrue);
      expect(item.isDownloading, isFalse);
    });
  });
}
