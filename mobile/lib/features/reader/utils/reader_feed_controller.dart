import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:manhwamaniacs/features/reader/models/reader_chapter.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';

/// Fetches one chapter's pages, or null when it cannot be had right now.
///
/// Null rather than throwing: a seam that cannot be crossed is not an error
/// state, it is a boundary the feed could not absorb — the reader keeps the
/// chapter they are in and the edge prompt stays as the way across.
typedef ReaderChapterLoader = Future<ReaderChapter?> Function(String chapterId);

/// What sits either side of a chapter, when only the server knows.
typedef ReaderNeighbourLoader = Future<({String? prev, String? next})> Function(
  String chapterId,
);

/// How many chapters of images a continuous read holds at once.
///
/// Three: the one being read plus one either side, which is what a seam needs
/// and is also the answer to R2's "never hold hundreds of chapters of images
/// in memory". Read-all is not a longer feed, it is this same window slid
/// along a longer list — a 300-chapter series and a 3-chapter one cost the
/// same.
const int kMaxFeedChapters = 3;

/// Owns the [ReaderFeed] for a continuous read: which chapters are loaded,
/// what comes next, and what to let go of (spec R1 and R2).
///
/// Deliberately a plain [ChangeNotifier] rather than a provider — the feed is
/// the state of one reading session and must not outlive it, and the screen
/// that owns the session is the natural owner.
///
/// Two ways to know what comes next. A plain read asks the server per chapter
/// ([neighboursOf]); Read-all is handed the whole ordered chapter list up
/// front ([order]) and needs no round trip to know where it is going. Same
/// controller either way, because the difference between "read this chapter"
/// and "read the whole series" turned out to be one list.
class ReaderFeedController extends ChangeNotifier {
  ReaderFeedController({
    required ReaderChapter anchor,
    required this.loadChapter,
    this.neighboursOf,
    List<String>? order,
    String? prev,
    String? next,
    this.maxChapters = kMaxFeedChapters,
    DateTime Function()? clock,
  })  : _feed = ReaderFeed.single(anchor),
        _order = order,
        _clock = clock ?? DateTime.now {
    _prevOf[anchor.id] = prev;
    _nextOf[anchor.id] = next;
  }

  final ReaderChapterLoader loadChapter;
  final ReaderNeighbourLoader? neighboursOf;
  final int maxChapters;

  /// The series' chapter ids in reading order, when the caller has them.
  /// Read-all always does; an ordinary read never does.
  ///
  /// Not final: Read-all opens the first chapter immediately and the order
  /// arrives behind it, which is the whole reason the mode can be entered on a
  /// 300-chapter series without a spinner in front of it.
  List<String>? _order;

  /// Hands the controller the series' chapter order once it has loaded. Until
  /// then the feed continues the ordinary way — by asking what comes next —
  /// so the reader is never waiting on this.
  ///
  /// Deliberately does NOT notify: knowing where the series goes changes
  /// nothing on screen, only what happens at the next boundary. Notifying
  /// would also mean a rebuild from inside a build (this is called as the
  /// order lands, mid-frame), which is not a thing.
  void setOrder(List<String> order) {
    if (listEquals(_order, order)) return;
    _order = order;
  }

  ReaderFeed _feed;
  ReaderFeed get feed => _feed;

  final Map<String, String?> _prevOf = {};
  final Map<String, String?> _nextOf = {};

  /// One request in flight per DIRECTION, not one overall.
  ///
  /// A single lock cost Read-all its opening seam: entering mid-series fires
  /// the backward trigger on the first frames (the reader is at flat index 0),
  /// and a forward extension raised while that was in flight simply returned
  /// and waited for another scroll event. Forward is the direction Read-all is
  /// about; it should never queue behind backward.
  bool _extendingForward = false;
  bool _extendingBackward = false;
  bool _disposed = false;

  /// Clock behind the retry backoff, injectable so a test can prove the backoff
  /// without sleeping through it.
  final DateTime Function() _clock;

  /// A chapter that would not load, and the earliest it is worth asking again.
  ///
  /// The forward trigger re-arms on every scroll notification, and at the end
  /// of the feed the reader sits exactly where overscroll bounces keep firing
  /// them — so a source that had just started refusing was asked again as fast
  /// as it could refuse. "Every attempt is a network round trip" bounds the
  /// rate to the round-trip time, which against a 429 is the wrong bound.
  final Map<String, DateTime> _retryAfter = {};
  final Map<String, int> _failures = {};

  static const Duration _firstRetryDelay = Duration(seconds: 2);
  static const Duration _maxRetryDelay = Duration(seconds: 30);

  /// Whether a chapter is being fetched right now. The reader does not wait on
  /// this — the seam is only ever *approached* while it resolves.
  bool get isExtending => _extendingForward || _extendingBackward;

  /// The chapter after the LAST one in the feed, and the one before the FIRST —
  /// where the edge prompts have to point.
  ///
  /// Not the anchor's neighbours: in a slid Read-all window the anchor left the
  /// feed long ago, and a run that dead-ends at chapter 30 offering "next
  /// chapter" for the anchor's neighbour sends the reader back to chapter 6.
  String? get nextBeyondFeed =>
      _feed.chapters.isEmpty ? null : _nextIdAfter(_feed.chapters.last.id);

  String? get previousBeforeFeed =>
      _feed.chapters.isEmpty ? null : _prevIdBefore(_feed.chapters.first.id);

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  /// Records what the caller already knows about a chapter's neighbours, so
  /// the anchor's own prev/next (which arrive after first paint, out of band —
  /// spec R3) are not re-fetched.
  ///
  /// Silent, for the same reason as [setOrder]: the neighbour keys are not on
  /// screen anywhere, they only unlock the next extension, and this is called
  /// from a build.
  void noteNeighbours(String chapterId, {String? prev, String? next}) {
    if (prev != null) _prevOf[chapterId] = prev;
    if (next != null) _nextOf[chapterId] = next;
  }

  /// Fold a re-resolved [chapter] back into the feed **in place**, keeping the
  /// window around it.
  ///
  /// The provider behind the anchor can resolve the same chapter again — the
  /// store answering where the network did a moment ago, or an equivalent
  /// value for no visible reason at all — and by then a Read-all run
  /// legitimately holds chapters either side of it. Rebuilding the controller
  /// for that would collapse the feed to this one chapter and put the reader
  /// back at whatever the route opened at, which after two or three chapters
  /// of reading is a jump backwards. Swapping one entry costs nothing and
  /// keeps everything already loaded and measured.
  ///
  /// A chapter the window has already released is not on screen and needs
  /// nothing: it is a no-op rather than a reason to reset.
  ///
  /// Silent, like [setOrder] and [noteNeighbours] and for the same reason —
  /// the caller is a `didUpdateWidget`, and the build that follows it reads
  /// [feed] anyway.
  void replaceChapter(ReaderChapter chapter) {
    final index = _feed.indexOfChapter(chapter.id);
    if (index < 0) return;
    if (_feed.chapters[index] == chapter) return;
    final chapters = [..._feed.chapters];
    chapters[index] = chapter;
    _feed = ReaderFeed.of(chapters);
  }

  String? _nextIdAfter(String chapterId) {
    final order = _order;
    if (order != null) {
      final index = order.indexOf(chapterId);
      if (index < 0 || index + 1 >= order.length) return null;
      return order[index + 1];
    }
    return _nextOf[chapterId];
  }

  String? _prevIdBefore(String chapterId) {
    final order = _order;
    if (order != null) {
      final index = order.indexOf(chapterId);
      if (index <= 0) return null;
      return order[index - 1];
    }
    return _prevOf[chapterId];
  }

  /// Load the chapter after the last one in the feed and append it — the
  /// forward seam. A no-op at the end of the series, while another extension
  /// is in flight, or when the chapter cannot be fetched.
  Future<void> extendForward() => _extend(forward: true);

  /// Load the chapter before the first one and prepend it — the backward
  /// seam. A boundary you can only cross one way is a trap, so this is not
  /// optional.
  Future<void> extendBackward() => _extend(forward: false);

  Future<void> _extend({required bool forward}) async {
    if (_disposed) return;
    if (forward ? _extendingForward : _extendingBackward) return;

    final edge = forward ? _feed.chapters.last.id : _feed.chapters.first.id;
    final targetId = forward ? _nextIdAfter(edge) : _prevIdBefore(edge);
    if (targetId == null || _feed.contains(targetId)) return;

    final retryAt = _retryAfter[targetId];
    if (retryAt != null && _clock().isBefore(retryAt)) return;

    if (forward) {
      _extendingForward = true;
    } else {
      _extendingBackward = true;
    }
    try {
      final chapter = await _loadOrNull(targetId);
      if (_disposed) return;
      if (chapter == null || chapter.pages.isEmpty) {
        _noteFailure(targetId);
        return;
      }
      _retryAfter.remove(targetId);
      _failures.remove(targetId);

      var next = forward
          ? _feed.withAppended(chapter)
          : _feed.withPrepended(chapter);

      // Release from the far end. The trigger says where the reader is — this
      // only ever runs because they approached one end — so the chapter to let
      // go of is unambiguous.
      final excess = next.chapters.length - maxChapters;
      if (excess > 0) {
        next = forward
            ? next.withoutLeadingChapters(excess)
            : next.withoutTrailingChapters(excess);
      }

      if (identical(next, _feed)) return;
      _feed = next;
      notifyListeners();
    } finally {
      if (forward) {
        _extendingForward = false;
      } else {
        _extendingBackward = false;
      }
    }

    // Only now, with the seam already open behind the reader.
    unawaited(_learnNeighbours(targetId));
  }

  /// The loader's contract is null rather than a throw, but [_extend] is only
  /// ever launched unawaited — a future that failed out of it is an unhandled
  /// async error in the reader, so a throw is absorbed here and treated as the
  /// refusal it is.
  Future<ReaderChapter?> _loadOrNull(String chapterId) async {
    try {
      return await loadChapter(chapterId);
    } catch (_) {
      return null;
    }
  }

  /// Learn what sits either side of [chapterId] — *after* its pages are on
  /// screen, never in front of them.
  ///
  /// Both loaders are disk-first, so a downloaded chapter is fully in hand the
  /// moment [loadChapter] returns. Awaiting prev/next before committing the
  /// feed put a network round trip back in front of a seam that needed no
  /// network at all (spec R3), and held the extension lock for its duration —
  /// on a flaky connection, the full connect timeout with the chapter sitting
  /// unused. Knowing what is beyond the NEXT chapter is not a precondition for
  /// showing this one.
  Future<void> _learnNeighbours(String chapterId) async {
    final loader = neighboursOf;
    if (loader == null || _order != null || _disposed) return;
    if (_prevOf.containsKey(chapterId) && _nextOf.containsKey(chapterId)) return;
    try {
      final neighbours = await loader(chapterId);
      if (_disposed) return;
      _prevOf[chapterId] = neighbours.prev;
      _nextOf[chapterId] = neighbours.next;
    } catch (_) {
      // Unknown neighbours cost the seam past this chapter, not this one.
    }
  }

  /// Back off from a chapter that would not come, doubling each time and
  /// capped, so a source that is refusing gets asked once in a while rather
  /// than once per scroll frame.
  void _noteFailure(String chapterId) {
    final attempts = (_failures[chapterId] ?? 0) + 1;
    _failures[chapterId] = attempts;
    var delay = _firstRetryDelay * (1 << (attempts - 1).clamp(0, 5));
    if (delay > _maxRetryDelay) delay = _maxRetryDelay;
    _retryAfter[chapterId] = _clock().add(delay);
  }
}
