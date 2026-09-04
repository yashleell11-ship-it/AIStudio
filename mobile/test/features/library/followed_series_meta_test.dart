import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/library/widgets/home/followed_series_card.dart';
import 'package:manhwamaniacs/features/updates/models/update_notification.dart';

UpdateNotification _notification({
  required int id,
  int? followedSeriesId,
  double? chapterNumber,
  bool isRead = false,
  DateTime? createdAt,
}) =>
    UpdateNotification(
      id: id,
      followedSeriesId: followedSeriesId,
      sourceId: 'asurascans',
      seriesKey: 'solo-leveling',
      chapterKey: '$id',
      chapterTitle: 'Chapter $id',
      chapterNumber: chapterNumber,
      isRead: isRead,
      createdAt: createdAt,
    );

void main() {
  group('FollowedSeriesMeta.indexBySeries', () {
    test('reduces the list to one entry per series in a single pass', () {
      final index = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, followedSeriesId: 1, chapterNumber: 120),
        _notification(id: 2, followedSeriesId: 1, chapterNumber: 121),
        _notification(id: 3, followedSeriesId: 99, chapterNumber: 400),
      ]);

      expect(index.keys, unorderedEquals(<int>[1, 99]));
      expect(index[1]!.latestChapterLabel, 'Chapter 121');
      expect(index[1]!.unreadCount, 2);
      expect(index[99]!.latestChapterLabel, 'Chapter 400');
    });

    test('a read notification counts toward latest but not toward unread', () {
      final index = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, followedSeriesId: 1, chapterNumber: 118),
        _notification(id: 2, followedSeriesId: 1, chapterNumber: 119, isRead: true),
      ]);

      expect(index[1]!.latestChapterLabel, 'Chapter 119');
      expect(index[1]!.unreadCount, 1);
    });

    test('falls back to created-at, then id, when numbers cannot decide', () {
      final byDate = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, followedSeriesId: 1, createdAt: DateTime.utc(2026, 1, 2)),
        _notification(id: 2, followedSeriesId: 1, createdAt: DateTime.utc(2026)),
      ]);
      expect(byDate[1]!.latestChapterLabel, 'Chapter 1');

      final byId = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, followedSeriesId: 1),
        _notification(id: 2, followedSeriesId: 1),
      ]);
      expect(byId[1]!.latestChapterLabel, 'Chapter 2');
    });

    test('skips notifications whose follow row is gone', () {
      final index = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, chapterNumber: 5),
      ]);

      expect(index, isEmpty);
    });

    test('a series with no notification is simply absent', () {
      final index = FollowedSeriesMeta.indexBySeries([
        _notification(id: 1, followedSeriesId: 1, chapterNumber: 5),
      ]);

      expect(index[2], isNull);
      expect(FollowedSeriesMeta.none.unreadCount, 0);
      expect(FollowedSeriesMeta.none.latestChapterLabel, isNull);
    });
  });
}
