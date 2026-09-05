import 'package:manhwamaniacs/core/utils/result.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest.dart';
import 'package:manhwamaniacs/features/reader/models/chapter_manifest_window.dart';
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

  /// The same plans for a bounded WINDOW of one series' chapters in a single
  /// round trip — `POST /reader/chapters/manifest`.
  ///
  /// POST rather than GET because the body is a list of opaque connector keys
  /// that routinely contain slashes and percent-encoding; twenty of those do
  /// not belong in a query string. It is still a read.
  ///
  /// This is what makes "download this whole series" reasonable: a 300-chapter
  /// series otherwise opens 300 requests before a single page lands, and
  /// pipelining those is what previously drew a real multi-minute 429 from a
  /// source. The endpoint sits on its own much tighter `bulk` bucket for that
  /// reason — one call is worth up to `max_chapters` upstream scrapes — so a
  /// caller spends a token on a window, never on a single chapter.
  ///
  /// The result is per-item, never all-or-nothing — see [ChapterManifestWindow].
  /// Over the server's cap the call fails with a `batch_too_large` [ApiError]
  /// naming it; every success echoes `max_chapters`, so a caller paces itself
  /// by the server's stride rather than a number compiled into the app.
  Future<Result<ChapterManifestWindow>> manifestWindow({
    required String sourceId,
    required String seriesKey,
    required List<String> chapterKeys,
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
