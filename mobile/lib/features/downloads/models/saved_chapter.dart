import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';

/// A `saved_chapters` row — one chapter's on-device download record for one
/// `(user, profile)` scope. Mirrors `docs/superpowers/specs/…mobile-source-native-design.md`
/// §3's schema.
class SavedChapter {
  const SavedChapter({
    required this.rowId,
    required this.scopeId,
    required this.sourceId,
    required this.seriesKey,
    required this.chapterKey,
    required this.chapterNumber,
    required this.title,
    required this.seriesTitle,
    required this.pageCount,
    required this.bytes,
    required this.state,
    required this.pinned,
    required this.readAt,
    required this.createdAt,
    required this.retryCount,
    required this.error,
  });

  final int rowId;
  final String scopeId;
  final String sourceId;
  final String seriesKey;
  final String chapterKey;
  final double? chapterNumber;
  final String? title;
  final String? seriesTitle;
  final int pageCount;
  final int bytes;
  final DownloadChapterState state;
  final bool pinned;

  /// Stamped when the chapter is finished reading; cleared on re-open. Drives
  /// the read-then-expire sweep. `null` means "never finished" — the sweep
  /// and pressure eviction must never touch such a row.
  final DateTime? readAt;
  final DateTime createdAt;

  /// Consecutive manifest/page failures for this chapter. Reset to 0 on a
  /// manual retry or a successful page fetch.
  final int retryCount;

  /// Last failure message, surfaced by the Downloads screen. Only meaningful
  /// when [state] is [DownloadChapterState.failed].
  final String? error;

  ChapterIdentity get identity =>
      (sourceId: sourceId, seriesKey: seriesKey, chapterKey: chapterKey);

  factory SavedChapter.fromRow(Map<String, Object?> row) => SavedChapter(
        rowId: row['id']! as int,
        scopeId: row['scope_id']! as String,
        sourceId: row['source_id']! as String,
        seriesKey: row['series_key']! as String,
        chapterKey: row['chapter_key']! as String,
        chapterNumber: (row['chapter_number'] as num?)?.toDouble(),
        title: row['title'] as String?,
        seriesTitle: row['series_title'] as String?,
        pageCount: row['page_count']! as int,
        bytes: row['bytes']! as int,
        state: DownloadChapterState.fromWire(row['state']! as String),
        pinned: (row['pinned']! as int) != 0,
        readAt: (row['read_at'] as String?) != null
            ? DateTime.parse(row['read_at']! as String)
            : null,
        createdAt: DateTime.parse(row['created_at']! as String),
        retryCount: row['retry_count']! as int,
        error: row['error'] as String?,
      );
}
