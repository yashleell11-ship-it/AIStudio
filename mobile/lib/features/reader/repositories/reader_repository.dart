import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';

/// Source-native reader endpoints (spec §4.1) — chapter manifests, reading
/// progress, and bookmarks. Identity throughout is the opaque
/// `(sourceId, seriesKey, chapterKey)` triple; never parsed or split.
abstract interface class ReaderRepository {
  Future<Result<ChapterManifest>> manifest({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
  });

  Future<Result<ReadingProgress>> saveProgress(ProgressPush push);

  Future<Result<({int saved, int advanced})>> saveProgressBatch(
    List<ProgressPush> pushes,
  );

  Future<Result<List<ReadingProgress>>> seriesProgress({
    required String sourceId,
    required String seriesKey,
  });

  /// Push a batch of offline bookmark ops — `POST /reader/bookmarks/batch`.
  ///
  /// The ONLY write path for bookmarks on this client, single deliberate taps
  /// included. `POST /reader/bookmark` would work while online, but a reader
  /// that used one path with signal and another without would have two sets of
  /// merge semantics to keep correct; the batch is a superset of the single
  /// create and is idempotent under replay, so there is one.
  Future<Result<BookmarkSyncResult>> syncBookmarks(List<BookmarkOp> ops);

  /// The pull half of bookmark sync, and the Bookmarks screen's refresh.
  ///
  /// [includeDeleted] is how a device *learns* about a delete made elsewhere:
  /// a tombstone arrives as a row, where an absence would be
  /// indistinguishable from a short page.
  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
    DateTime? since,
    bool includeDeleted = false,
    int? limit,
  });

  Future<Result<void>> deleteBookmark(int bookmarkId);
}
