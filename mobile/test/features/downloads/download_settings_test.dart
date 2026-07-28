import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_settings.dart';

void main() {
  group('DownloadSettings.fromJson', () {
    test('parses the float fields the server actually sends', () {
      // Verbatim shape of GET /downloads/settings with the server defaults
      // (backend/core/config.py:64-74). retry delay and timeout are declared
      // `float`, so they arrive as 0.75 / 30.0 and jsonDecode yields doubles —
      // the old `as int` cast threw here on every single response, which is why
      // the download settings section only ever showed its error card.
      final json = jsonDecode('''
        {
          "download_concurrent_chapters": 1,
          "download_page_concurrency": 4,
          "download_retry_count": 4,
          "download_retry_delay_seconds": 0.75,
          "download_timeout_seconds": 30.0,
          "active_download_count": 2
        }
      ''') as Map<String, dynamic>;

      final settings = DownloadSettings.fromJson(json);

      expect(settings.concurrentChapters, 1);
      expect(settings.pageConcurrency, 4);
      expect(settings.retryCount, 4);
      expect(settings.retryDelaySeconds, 0.75);
      expect(settings.timeoutSeconds, 30.0);
      expect(settings.activeDownloadCount, 2);
    });

    test('accepts whole numbers for the float fields too', () {
      // A settings.json edited by hand can persist `5` rather than `5.0`, and
      // jsonDecode then hands back an int.
      final json = jsonDecode('''
        {
          "download_concurrent_chapters": 3,
          "download_page_concurrency": 8,
          "download_retry_count": 0,
          "download_retry_delay_seconds": 1,
          "download_timeout_seconds": 30,
          "active_download_count": 0
        }
      ''') as Map<String, dynamic>;

      final settings = DownloadSettings.fromJson(json);

      expect(settings.retryDelaySeconds, 1.0);
      expect(settings.timeoutSeconds, 30.0);
    });

    test('round-trips through toUpdateJson without losing the fractions', () {
      const settings = DownloadSettings(
        concurrentChapters: 2,
        pageConcurrency: 6,
        retryCount: 4,
        retryDelaySeconds: 0.75,
        timeoutSeconds: 12.5,
        activeDownloadCount: 9,
      );

      final body = settings.toUpdateJson();

      expect(body['download_retry_delay_seconds'], 0.75);
      expect(body['download_timeout_seconds'], 12.5);
      // active_download_count is server-computed and must not be sent back.
      expect(body.containsKey('active_download_count'), isFalse);
    });
  });

  group('DownloadSettings.copyWith', () {
    test('changes one field and leaves the rest alone', () {
      const settings = DownloadSettings(
        concurrentChapters: 1,
        pageConcurrency: 4,
        retryCount: 4,
        retryDelaySeconds: 0.75,
        timeoutSeconds: 30.0,
        activeDownloadCount: 0,
      );

      final updated = settings.copyWith(concurrentChapters: 5);

      expect(updated.concurrentChapters, 5);
      expect(updated.pageConcurrency, 4);
      expect(updated.retryCount, 4);
      expect(updated.retryDelaySeconds, 0.75);
      expect(updated.timeoutSeconds, 30.0);
      expect(updated.activeDownloadCount, 0);
    });
  });
}
