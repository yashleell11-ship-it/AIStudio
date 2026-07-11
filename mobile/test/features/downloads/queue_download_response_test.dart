import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/queue_download_response.dart';

void main() {
  group('QueueDownloadResponse.fromJson', () {
    test('parses queued ids and skipped chapter ids', () {
      final response = QueueDownloadResponse.fromJson({
        'queued': [1, 2, 3],
        'skipped': ['ch-1', 'ch-2'],
        'warnings': ['Low disk space'],
      });

      expect(response.queued, [1, 2, 3]);
      expect(response.skipped, ['ch-1', 'ch-2']);
      expect(response.warnings, ['Low disk space']);
    });

    test('defaults missing lists to empty', () {
      final response = QueueDownloadResponse.fromJson({});

      expect(response.queued, isEmpty);
      expect(response.skipped, isEmpty);
      expect(response.warnings, isEmpty);
    });
  });
}
