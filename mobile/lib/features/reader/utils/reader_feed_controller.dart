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
  })  : _feed = ReaderFeed.single(anchor),
        _order = order {
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

  bool _extending = false;
  bool _disposed = false;

  /// Whether a chapter is being fetched right now. The reader does not wait on
  /// this — the seam is only ever *approached* while it resolves.
  bool get isExtending => _extending;

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
    if (_extending || _disposed) return;

    final edge = forward ? _feed.chapters.last.id : _feed.chapters.first.id;
    final targetId = forward ? _nextIdAfter(edge) : _prevIdBefore(edge);
    if (targetId == null || _feed.contains(targetId)) return;

    _extending = true;
    try {
      final chapter = await loadChapter(targetId);
      if (_disposed) return;
      if (chapter == null || chapter.pages.isEmpty) return;

      // Learn what is beyond the new chapter now, so the seam AFTER it is
      // already known by the time the reader gets near it.
      if (_order == null && neighboursOf != null) {
        try {
          final neighbours = await neighboursOf!(targetId);
          if (_disposed) return;
          _prevOf[targetId] = neighbours.prev;
          _nextOf[targetId] = neighbours.next;
        } catch (_) {
          // Unknown neighbours cost the seam past this chapter, not this one.
        }
      }

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
      _extending = false;
    }
  }
}
