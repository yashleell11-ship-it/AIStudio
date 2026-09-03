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

  Future<Result<Bookmark>> addBookmark({
    required String sourceId,
    required String seriesKey,
    required String chapterKey,
    required int page,
    String? note,
  });

  Future<Result<List<Bookmark>>> listBookmarks({
    String? sourceId,
    String? seriesKey,
  });

  Future<Result<void>> deleteBookmark(int bookmarkId);
}
