import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/utils/source_chapter_download_status.dart';

DownloadItem _item({
  required String chapterId,
  required String status,
  DateTime? updatedAt,
}) =>
    DownloadItem(
      id: chapterId.hashCode,
      source: 'mangadex',
      seriesId: 'manga-1',
      chapterId: chapterId,
      seriesTitle: 'Solo Leveling',
      chapterTitle: 'Chapter',
      status: status,
      progress: status == 'completed' ? 1 : 0.5,
      pagesDone: 5,
      pagesTotal: 10,
      bytesDownloaded: 1024,
      createdAt: DateTime.utc(2024),
      updatedAt: updatedAt ?? DateTime.utc(2024),
      priority: 0,
      retryCount: 0,
    );

void main() {
  group('buildSourceChapterDownloadLookup', () {
    test('maps latest download per chapter for matching source series', () {
      final lookup = buildSourceChapterDownloadLookup(
        sourceId: 'mangadex',
        seriesId: 'manga-1',
        items: [
          _item(
            chapterId: 'manga-1:1',
            status: 'queued',
            updatedAt: DateTime.utc(2024, 1, 2),
          ),
          _item(
            chapterId: 'manga-1:2',
            status: 'completed',
            updatedAt: DateTime.utc(2024, 1, 3),
          ),
          _item(
            chapterId: 'manga-1:3',
            status: 'downloading',
            updatedAt: DateTime.utc(2024, 1, 4),
          ),
          _item(
            chapterId: 'other-series:1',
            status: 'completed',
            updatedAt: DateTime.utc(2024, 1, 5),
          ),
        ],
      );

      expect(lookup.statusFor('manga-1:1'), SourceChapterDownloadUiStatus.queued);
      expect(lookup.statusFor('manga-1:2'), SourceChapterDownloadUiStatus.completed);
      expect(lookup.statusFor('manga-1:3'), SourceChapterDownloadUiStatus.downloading);
      expect(lookup.statusFor('missing'), SourceChapterDownloadUiStatus.none);
    });

    test('uses the newest download when multiple exist for one chapter', () {
      final lookup = buildSourceChapterDownloadLookup(
        sourceId: 'mangadex',
        seriesId: 'manga-1',
        items: [
          _item(
            chapterId: 'manga-1:1',
            status: 'completed',
            updatedAt: DateTime.utc(2024),
          ),
          _item(
            chapterId: 'manga-1:1',
            status: 'failed',
            updatedAt: DateTime.utc(2024, 1, 2),
          ),
        ],
      );

      expect(lookup.statusFor('manga-1:1'), SourceChapterDownloadUiStatus.failed);
      expect(lookup.isRetryable('manga-1:1'), isTrue);
    });

    test('ignores cancelled downloads', () {
      final lookup = buildSourceChapterDownloadLookup(
        sourceId: 'mangadex',
        seriesId: 'manga-1',
        items: [
          _item(chapterId: 'manga-1:1', status: 'cancelled'),
        ],
      );

      expect(lookup.statusFor('manga-1:1'), SourceChapterDownloadUiStatus.none);
    });
  });

  group('SourceChapterDownloadLookup actions', () {
    test('disables download for queued, downloading, and completed', () {
      const lookup = SourceChapterDownloadLookup(
        statusByChapterId: {
          'queued': SourceChapterDownloadUiStatus.queued,
          'downloading': SourceChapterDownloadUiStatus.downloading,
          'completed': SourceChapterDownloadUiStatus.completed,
          'failed': SourceChapterDownloadUiStatus.failed,
          'none': SourceChapterDownloadUiStatus.none,
        },
      );

      expect(lookup.isDownloadDisabled('queued'), isTrue);
      expect(lookup.isDownloadDisabled('downloading'), isTrue);
      expect(lookup.isDownloadDisabled('completed'), isTrue);
      expect(lookup.isDownloadDisabled('failed'), isFalse);
      expect(lookup.isDownloadDisabled('none'), isFalse);
    });

    test('labels all ui statuses', () {
      expect(
        sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus.none),
        'Download',
      );
      expect(
        sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus.queued),
        'Queued',
      );
      expect(
        sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus.downloading),
        'Downloading',
      );
      expect(
        sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus.completed),
        'Completed',
      );
      expect(
        sourceChapterDownloadStatusLabel(SourceChapterDownloadUiStatus.failed),
        'Failed',
      );
    });
  });

  group('uiStatusFromDownloadItem', () {
    test('maps paused downloads to queued ui status', () {
      expect(
        uiStatusFromDownloadItem(_item(chapterId: 'manga-1:1', status: 'paused')),
        SourceChapterDownloadUiStatus.queued,
      );
    });
  });
}
