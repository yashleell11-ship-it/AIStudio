import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';

/// The server's cap on one `POST /reader/progress/batch`
/// (`PROGRESS_BATCH_MAX_ITEMS` in `backend/routes/reader.py`). Over it the
/// server answers 413 `batch_too_large` and merges nothing, so a flush with
/// more than this to say sends several batches rather than taking one 413 for
/// the lot — the same rule `kBookmarkBatchMaxItems` states for bookmarks.
const int kProgressBatchMaxItems = 200;

/// One pending outbox row: the id to clear it by, and the push it holds.
typedef PendingProgress = (int outboxId, ProgressPush push);

/// A collapsed group: the single push to send, and every outbox row it stands
/// for — all of which are settled once that push is accepted.
typedef CollapsedProgress = ({List<int> outboxIds, ProgressPush push});

/// Collapses [pending] to one push per `(source, series, chapter)`, oldest
/// group first.
///
/// The manga reader enqueues roughly one row per page settled on, so an
/// evening offline is hundreds of rows saying the same thing about the same
/// chapter: progress is furthest-wins, and every row before the furthest one
/// for a chapter is already implied by it. Sending them individually costs a
/// batch slot and a merge each, for the state the furthest row alone produces.
///
/// The merge here is deliberately the server's (`merge_progress` in
/// `backend/services/progress_service.py`), so collapsing on the device and
/// sending every row separately reach the same stored state:
///
/// * position is the furthest `last_page` reached, never the latest written;
/// * `scroll_offset_px` comes from that winning row, since the server takes
///   the offset of whichever push owns the position;
/// * `is_completed` is sticky — finishing a chapter and scrolling back up
///   must not un-finish it;
/// * `time_spent_seconds` is SUMMED, because the server accumulates it. It is
///   a per-push delta, so dropping the losers' deltas would discard most of
///   the session's reading time.
List<CollapsedProgress> collapseProgressOutbox(List<PendingProgress> pending) {
  // A record key, not a joined string: series and chapter keys are opaque
  // source strings that can hold whatever the source put in a URL, and a
  // separator that appears inside one would merge two different chapters.
  final order = <(String, String, String)>[];
  final groups = <(String, String, String), CollapsedProgress>{};

  for (final (outboxId, push) in pending) {
    final key = (push.sourceId, push.seriesKey, push.chapterKey);
    final existing = groups[key];
    if (existing == null) {
      order.add(key);
      groups[key] = (outboxIds: [outboxId], push: push);
      continue;
    }
    groups[key] = (
      outboxIds: [...existing.outboxIds, outboxId],
      push: _furthest(existing.push, push),
    );
  }

  return [for (final key in order) groups[key]!];
}

/// Slices [items] into batches no larger than [max].
List<List<T>> chunkForBatch<T>(
  List<T> items, {
  int max = kProgressBatchMaxItems,
}) {
  final size = max < 1 ? 1 : max;
  return [
    for (var start = 0; start < items.length; start += size)
      items.sublist(start, (start + size).clamp(0, items.length)),
  ];
}

ProgressPush _furthest(ProgressPush a, ProgressPush b) {
  final winner = b.lastPage > a.lastPage ? b : a;
  final loser = identical(winner, a) ? b : a;
  return ProgressPush(
    sourceId: winner.sourceId,
    seriesKey: winner.seriesKey,
    chapterKey: winner.chapterKey,
    chapterNumber: winner.chapterNumber ?? loser.chapterNumber,
    lastPage: winner.lastPage,
    pageCount: a.pageCount > b.pageCount ? a.pageCount : b.pageCount,
    scrollOffsetPx: winner.scrollOffsetPx,
    isCompleted: a.isCompleted || b.isCompleted,
    timeSpentSeconds: a.timeSpentSeconds + b.timeSpentSeconds,
    lastReadAt: _latest(a.lastReadAt, b.lastReadAt),
  );
}

DateTime? _latest(DateTime? a, DateTime? b) {
  if (a == null) return b;
  if (b == null) return a;
  return a.isAfter(b) ? a : b;
}
