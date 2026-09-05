import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/utils/progress_outbox_batch.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';

ProgressPush _push({
  String chapterKey = 'ch',
  int lastPage = 1,
  int pageCount = 20,
  int scrollOffsetPx = 0,
  bool isCompleted = false,
  int timeSpentSeconds = 0,
  DateTime? lastReadAt,
}) =>
    ProgressPush(
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: chapterKey,
      chapterNumber: 1,
      lastPage: lastPage,
      pageCount: pageCount,
      scrollOffsetPx: scrollOffsetPx,
      isCompleted: isCompleted,
      timeSpentSeconds: timeSpentSeconds,
      lastReadAt: lastReadAt,
    );

void main() {
  group('collapseProgressOutbox', () {
    test('an empty outbox collapses to nothing', () {
      expect(collapseProgressOutbox(const []), isEmpty);
    });

    test('one row per chapter, keeping the furthest page', () {
      final collapsed = collapseProgressOutbox([
        (1, _push(lastPage: 3)),
        (2, _push(lastPage: 9)),
        (3, _push(lastPage: 7)),
      ]);

      expect(collapsed, hasLength(1));
      // Furthest, not latest: scrolling back up must not rewind the server.
      expect(collapsed.single.push.lastPage, 9);
      // Every collapsed row is settled by the one push that replaced it.
      expect(collapsed.single.outboxIds, [1, 2, 3]);
    });

    test('different chapters stay separate, oldest group first', () {
      final collapsed = collapseProgressOutbox([
        (1, _push(chapterKey: 'c1', lastPage: 4)),
        (2, _push(chapterKey: 'c2', lastPage: 2)),
        (3, _push(chapterKey: 'c1', lastPage: 6)),
      ]);

      expect(collapsed.map((e) => e.push.chapterKey), ['c1', 'c2']);
      expect(collapsed.first.push.lastPage, 6);
      expect(collapsed.first.outboxIds, [1, 3]);
    });

    test('reading time is summed, because the server accumulates it', () {
      final collapsed = collapseProgressOutbox([
        (1, _push(lastPage: 2, timeSpentSeconds: 11)),
        (2, _push(lastPage: 5, timeSpentSeconds: 13)),
        (3, _push(lastPage: 4, timeSpentSeconds: 7)),
      ]);

      // Dropping the losing rows' deltas would throw away most of a session.
      expect(collapsed.single.push.timeSpentSeconds, 31);
    });

    test('completion is sticky and the winning row owns the scroll offset', () {
      final collapsed = collapseProgressOutbox([
        (1, _push(lastPage: 20, isCompleted: true, scrollOffsetPx: 8000)),
        (2, _push(lastPage: 3, scrollOffsetPx: 120)),
      ]);

      expect(collapsed.single.push.isCompleted, isTrue);
      expect(collapsed.single.push.lastPage, 20);
      expect(collapsed.single.push.scrollOffsetPx, 8000);
    });

    test('the latest capture time survives the collapse', () {
      final early = DateTime.utc(2026, 9, 1, 10);
      final late = DateTime.utc(2026, 9, 1, 12);
      final collapsed = collapseProgressOutbox([
        (1, _push(lastPage: 9, lastReadAt: late)),
        (2, _push(lastPage: 4, lastReadAt: early)),
      ]);

      expect(collapsed.single.push.lastReadAt, late);
    });
  });

  group('chunkForBatch', () {
    test('nothing to send is no batches at all', () {
      expect(chunkForBatch(const <int>[]), isEmpty);
    });

    test('a batch at the cap is sent whole', () {
      final items = List.generate(kProgressBatchMaxItems, (i) => i);
      expect(chunkForBatch(items), hasLength(1));
    });

    test('over the cap is split rather than refused as one 413', () {
      final items = List.generate(kProgressBatchMaxItems * 2 + 1, (i) => i);
      final chunks = chunkForBatch(items);

      expect(chunks, hasLength(3));
      expect(chunks[0], hasLength(kProgressBatchMaxItems));
      expect(chunks[1], hasLength(kProgressBatchMaxItems));
      expect(chunks[2], hasLength(1));
      // Order and contents survive the split exactly.
      expect(chunks.expand((chunk) => chunk), items);
    });

    test('a nonsensical cap still makes progress rather than looping', () {
      expect(chunkForBatch([1, 2, 3], max: 0), hasLength(3));
    });
  });
}
