import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/utils/download_queue_status.dart';

DownloadItem _item({
  required int id,
  required String status,
  int pagesDone = 0,
  int pagesTotal = 10,
  double progress = 0,
}) =>
    DownloadItem(
      id: id,
      source: 'test',
      seriesId: 'solo',
      chapterId: 'ch-$id',
      seriesTitle: 'Solo Leveling',
      chapterTitle: 'Chapter $id',
      status: status,
      progress: progress,
      pagesDone: pagesDone,
      pagesTotal: pagesTotal,
      bytesDownloaded: 1024,
      createdAt: DateTime.utc(2024),
      updatedAt: DateTime.utc(2024),
      priority: 0,
      retryCount: 0,
    );

void main() {
  group('downloadQueueDisplayStatus', () {
    test('maps core backend statuses', () {
      expect(
        downloadQueueDisplayStatus(_item(id: 1, status: 'queued')),
        DownloadQueueDisplayStatus.queued,
      );
      expect(
        downloadQueueDisplayStatus(_item(id: 2, status: 'downloading')),
        DownloadQueueDisplayStatus.downloading,
      );
      expect(
        downloadQueueDisplayStatus(_item(id: 3, status: 'completed')),
        DownloadQueueDisplayStatus.completed,
      );
      expect(
        downloadQueueDisplayStatus(_item(id: 4, status: 'failed')),
        DownloadQueueDisplayStatus.failed,
      );
    });

    test('derives importing while status remains downloading', () {
      expect(
        downloadQueueDisplayStatus(
          _item(
            id: 5,
            status: 'downloading',
            pagesDone: 10,
            progress: 100,
          ),
        ),
        DownloadQueueDisplayStatus.importing,
      );
    });

    test('derives verifying near completion', () {
      expect(
        downloadQueueDisplayStatus(
          _item(
            id: 6,
            status: 'downloading',
            pagesDone: 9,
            progress: 95,
          ),
        ),
        DownloadQueueDisplayStatus.verifying,
      );
    });
  });

  group('downloadRowActions', () {
    test('shows pause for queued and downloading items', () {
      expect(downloadRowActions(_item(id: 1, status: 'queued')).showPause, isTrue);
      expect(downloadRowActions(_item(id: 2, status: 'downloading')).showPause, isTrue);
    });

    test('shows resume only for paused items', () {
      expect(downloadRowActions(_item(id: 1, status: 'paused')).showResume, isTrue);
      expect(downloadRowActions(_item(id: 2, status: 'failed')).showResume, isFalse);
    });

    test('shows retry only for failed items', () {
      expect(downloadRowActions(_item(id: 1, status: 'failed')).showRetry, isTrue);
      expect(downloadRowActions(_item(id: 2, status: 'paused')).showRetry, isFalse);
    });

    test('hides cancel for completed and cancelled items', () {
      expect(downloadRowActions(_item(id: 1, status: 'completed')).showCancel, isFalse);
      expect(downloadRowActions(_item(id: 2, status: 'cancelled')).showCancel, isFalse);
      expect(downloadRowActions(_item(id: 3, status: 'failed')).showCancel, isTrue);
    });
  });

  group('countDownloadQueueStatuses', () {
    test('counts display phases across items', () {
      final counts = countDownloadQueueStatuses([
        _item(id: 1, status: 'queued'),
        _item(id: 2, status: 'downloading'),
        _item(
          id: 3,
          status: 'downloading',
          pagesDone: 10,
          progress: 100,
        ),
        _item(id: 4, status: 'failed'),
        _item(id: 5, status: 'completed'),
      ]);

      expect(counts[DownloadQueueDisplayStatus.queued], 1);
      expect(counts[DownloadQueueDisplayStatus.downloading], 1);
      expect(counts[DownloadQueueDisplayStatus.importing], 1);
      expect(counts[DownloadQueueDisplayStatus.failed], 1);
      expect(counts[DownloadQueueDisplayStatus.completed], 1);
    });
  });
}
