/// Longest gap between two progress pushes that still counts as reading.
///
/// A reader left open is not a reader being read: the phone locks, the app is
/// backgrounded, or the book sits on the table until morning. Capping
/// under-reports one genuinely slow page and refuses to invent an afternoon,
/// which is the right way round for a statistic.
const int kMaxReadingGapSeconds = 300;

/// Wall-clock reading time between two progress pushes.
///
/// The server accumulates `time_spent_seconds` and derives every reading
/// session's duration from it (`_apply_one` in
/// `backend/services/progress_service.py` offsets `started_at` by the delta),
/// so a client that never sends one leaves the statistics screen's time-read
/// figures structurally zero rather than merely wrong. This is the client's
/// half of it.
///
/// [elapsed] returns the delta since the previous call, never a running
/// total: the server adds what it is sent, so a cumulative figure would
/// inflate on every replayed push.
class ReadingClock {
  ReadingClock(DateTime startedAt) : _mark = startedAt;

  DateTime _mark;

  /// Seconds read since the previous call, or since the reader opened.
  int elapsed(DateTime now) {
    final gap = now.difference(_mark);
    if (gap.isNegative) {
      // The device clock moved backwards (NTP, a timezone-less manual set).
      // Crediting a negative reading session is worse than crediting none.
      _mark = now;
      return 0;
    }
    if (gap.inSeconds > kMaxReadingGapSeconds) {
      _mark = now;
      return kMaxReadingGapSeconds;
    }
    // Advance the mark only by the whole seconds actually credited, so the
    // sub-second remainder carries into the next push. Pages settle every
    // 500ms; truncating each time would report zero for a fast read.
    final seconds = gap.inSeconds;
    _mark = _mark.add(Duration(seconds: seconds));
    return seconds;
  }
}
