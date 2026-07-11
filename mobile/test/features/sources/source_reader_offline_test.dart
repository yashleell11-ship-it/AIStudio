import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/sources/providers/source_reader_provider.dart';
import 'package:manhwamaniacs/features/sources/utils/source_reader_offline.dart';

DownloadItem _completedDownload({
  required String chapterId,
  required int localChapterId,
}) {
  final now = DateTime.utc(2026);
  return DownloadItem(
    id: 1,
    source: 'mangadex',
    seriesId: 'series-1',
    chapterId: chapterId,
    seriesTitle: 'Series',
    chapterTitle: 'Chapter',
    status: 'completed',
    progress: 1,
    pagesDone: 10,
    pagesTotal: 10,
    bytesDownloaded: 1000,
    localChapterId: localChapterId,
    createdAt: now,
    updatedAt: now,
    priority: 0,
    retryCount: 0,
  );
}

void main() {
  group('source_reader_offline', () {
    test('findCompletedSourceDownload returns latest completed item', () {
      final older = _completedDownload(chapterId: 'ch-1', localChapterId: 10);
      final newer = DownloadItem(
        id: 2,
        source: older.source,
        seriesId: older.seriesId,
        chapterId: older.chapterId,
        seriesTitle: older.seriesTitle,
        chapterTitle: older.chapterTitle,
        status: older.status,
        progress: older.progress,
        pagesDone: older.pagesDone,
        pagesTotal: older.pagesTotal,
        bytesDownloaded: older.bytesDownloaded,
        localChapterId: 11,
        createdAt: older.createdAt,
        updatedAt: DateTime.utc(2026, 2),
        priority: older.priority,
        retryCount: older.retryCount,
      );

      final match = findCompletedSourceDownload(
        sourceId: 'mangadex',
        seriesId: 'series-1',
        chapterId: 'ch-1',
        items: [older, newer],
      );

      expect(match?.localChapterId, 11);
    });

    test('findCompletedSourceDownload ignores non-completed items', () {
      final now = DateTime.utc(2026);
      final queued = DownloadItem(
        id: 3,
        source: 'mangadex',
        seriesId: 'series-1',
        chapterId: 'ch-2',
        seriesTitle: 'Series',
        chapterTitle: 'Chapter',
        status: 'queued',
        progress: 0,
        pagesDone: 0,
        pagesTotal: 0,
        bytesDownloaded: 0,
        localChapterId: 12,
        createdAt: now,
        updatedAt: now,
        priority: 0,
        retryCount: 0,
      );

      expect(
        findCompletedSourceDownload(
          sourceId: 'mangadex',
          seriesId: 'series-1',
          chapterId: 'ch-2',
          items: [queued],
        ),
        isNull,
      );
    });

    test('SourceReaderChapterKey equality is stable', () {
      const SourceReaderChapterKey a = (
        sourceId: 'src',
        seriesId: 'series',
        chapterId: 'ch',
      );
      const SourceReaderChapterKey b = (
        sourceId: 'src',
        seriesId: 'series',
        chapterId: 'ch',
      );
      expect(a, equals(b));
    });
  });
}
