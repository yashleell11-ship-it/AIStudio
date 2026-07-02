import 'package:aistudio_mobile/features/downloads/models/queue_download_response.dart';
import 'package:aistudio_mobile/features/downloads/utils/queue_download_feedback.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('queueDownloadFeedbackMessage', () {
    test('shows queued and skipped counts', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(
          queued: [1, 2],
          skipped: ['ch-3'],
        ),
      );

      expect(message, 'Queued 2 chapters\nSkipped 1 already downloaded');
    });

    test('shows only queued when nothing skipped', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [1], skipped: []),
      );

      expect(message, 'Queued 1 chapter');
    });

    test('shows only skipped when nothing queued', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [], skipped: ['ch-1', 'ch-2']),
      );

      expect(message, 'Skipped 2 already downloaded');
    });

    test('shows fallback when response is empty', () {
      final message = queueDownloadFeedbackMessage(
        const QueueDownloadResponse(queued: [], skipped: []),
      );

      expect(message, 'No chapters queued');
    });
  });
}
