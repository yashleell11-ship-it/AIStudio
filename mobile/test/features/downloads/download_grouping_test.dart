import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_item.dart';
import 'package:manhwamaniacs/features/downloads/utils/download_grouping.dart';

DownloadItem _item({
  required int id,
  required String status,
  String seriesId = 'solo',
  String source = 'test',
}) {
  return DownloadItem(
    id: id,
    source: source,
    seriesId: seriesId,
    chapterId: 'ch-$id',
    seriesTitle: 'Solo Leveling',
    chapterTitle: 'Chapter $id',
    status: status,
    progress: 10,
    pagesDone: 1,
    pagesTotal: 10,
    bytesDownloaded: 1000,
    createdAt: DateTime.utc(2024),
    updatedAt: DateTime.utc(2024),
    priority: 0,
    retryCount: 0,
  );
}

void main() {
  group('download_grouping', () {
    test('groups items by source and series', () {
      final groups = groupDownloadsBySeries([
        _item(id: 1, status: 'downloading'),
        _item(id: 2, status: 'queued'),
        _item(id: 3, status: 'queued', seriesId: 'other'),
      ]);

      expect(groups.length, 2);
      expect(groups.first.items.length, 2);
      expect(groups.first.active, 1);
      expect(groups.first.queued, 1);
    });

    test('visibleGroupItems hides completed chapters', () {
      final groups = groupDownloadsBySeries([
        _item(id: 1, status: 'downloading'),
        _item(id: 2, status: 'completed'),
      ]);

      expect(visibleGroupItems(groups.first).length, 1);
    });
  });
}
