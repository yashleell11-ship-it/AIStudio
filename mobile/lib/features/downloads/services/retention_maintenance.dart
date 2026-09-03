import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_deletion.dart';
import 'package:sqflite/sqflite.dart';

/// Identifies exactly one chapter row: which profile downloaded it, plus its
/// content identity.
typedef ScopedChapterIdentity = ({String scopeId, ChapterIdentity id});

/// Cross-profile storage maintenance: the read-then-expire sweep and cap
/// pressure-eviction. Unlike [DownloadsStore] (bound to one profile's scope
/// for isolation), this operates across every scope on the device — because
/// the storage cap and the free-space floor are **device properties, not
/// per-profile ones** (spec §3b): two profiles share one physical disk, so
/// staying under a shared budget has to be able to reclaim any profile's
/// aged-out chapters, not just the one currently in the foreground.
///
/// This never *displays* another profile's content — it only deletes bytes
/// that are already past their own read-then-expire timer or being evicted
/// under pressure, the same operation [DownloadsStore.deleteDownload]
/// performs for a single scope. Nothing here is reachable from a screen; it
/// is driven only by the launch/resume sweep and the "Free up space" action.
class RetentionMaintenance {
  RetentionMaintenance({required this.database, required this.blobStore});

  final Future<Database> database;
  final Future<BlobStore> blobStore;

  /// Real, dedup-aware disk usage — what the storage cap is enforced
  /// against. Not a per-scope sum: two profiles sharing a chapter contribute
  /// its bytes once, exactly like the disk does.
  Future<int> totalDeviceBytes() async {
    final db = await database;
    final result = await db.rawQuery(
      'SELECT SUM(${DownloadsSchema.colSize}) AS total FROM ${DownloadsSchema.blobs}',
    );
    return (result.first['total'] as num?)?.toInt() ?? 0;
  }

  /// Deletes every chapter whose read-then-expire timer has elapsed, across
  /// every profile. `null` [interval] disables the sweep entirely (the
  /// Settings "Off" option) without touching cap-pressure eviction.
  ///
  /// Returns how many chapters were deleted.
  Future<int> sweepExpired({
    required Duration? interval,
    ScopedChapterIdentity? excludeOpen,
  }) async {
    if (interval == null) return 0;
    final db = await database;
    final blob = await blobStore;
    final cutoff = DateTime.now().toUtc().subtract(interval);

    final rows = await db.query(
      DownloadsSchema.savedChapters,
      columns: [
        DownloadsSchema.colId,
        DownloadsSchema.colScopeId,
        DownloadsSchema.colSourceId,
        DownloadsSchema.colSeriesKey,
        DownloadsSchema.colChapterKey,
      ],
      where: '${DownloadsSchema.colPinned} = 0 AND ${DownloadsSchema.colReadAt} IS NOT NULL '
          'AND ${DownloadsSchema.colReadAt} <= ?',
      whereArgs: [cutoff.toIso8601String()],
    );

    var deleted = 0;
    for (final row in rows) {
      if (_isExcluded(row, excludeOpen)) continue;
      await deleteChapterAndBlobs(
        db: db,
        blobStore: blob,
        chapterRowId: row[DownloadsSchema.colId]! as int,
        scopeId: row[DownloadsSchema.colScopeId]! as String,
      );
      deleted++;
    }
    return deleted;
  }

  /// Deletes already-read, unpinned chapters — globally oldest `read_at`
  /// first — until total device usage is at or under [targetBytes]. Never
  /// touches a pinned series or a chapter that has not been read
  /// (`read_at IS NULL`): if pressure remains after every eligible chapter is
  /// gone, that pressure is left in place rather than reaching for unread or
  /// pinned content.
  ///
  /// Returns how many chapters were deleted.
  Future<int> evictOldestReadFirst({
    required int targetBytes,
    ScopedChapterIdentity? excludeOpen,
  }) async {
    final db = await database;
    final blob = await blobStore;
    var deleted = 0;

    while (await totalDeviceBytes() > targetBytes) {
      final rows = await db.query(
        DownloadsSchema.savedChapters,
        columns: [
          DownloadsSchema.colId,
          DownloadsSchema.colScopeId,
          DownloadsSchema.colSourceId,
          DownloadsSchema.colSeriesKey,
          DownloadsSchema.colChapterKey,
        ],
        where: '${DownloadsSchema.colPinned} = 0 AND ${DownloadsSchema.colReadAt} IS NOT NULL',
        orderBy: '${DownloadsSchema.colReadAt} ASC',
        limit: excludeOpen == null ? 1 : 5,
      );

      final candidate = rows.firstWhere(
        (row) => !_isExcluded(row, excludeOpen),
        orElse: () => <String, Object?>{},
      );
      if (candidate.isEmpty) break; // Nothing left that's safe to evict.

      await deleteChapterAndBlobs(
        db: db,
        blobStore: blob,
        chapterRowId: candidate[DownloadsSchema.colId]! as int,
        scopeId: candidate[DownloadsSchema.colScopeId]! as String,
      );
      deleted++;
    }
    return deleted;
  }

  bool _isExcluded(Map<String, Object?> row, ScopedChapterIdentity? excludeOpen) {
    if (excludeOpen == null) return false;
    return row[DownloadsSchema.colScopeId] == excludeOpen.scopeId &&
        row[DownloadsSchema.colSourceId] == excludeOpen.id.sourceId &&
        row[DownloadsSchema.colSeriesKey] == excludeOpen.id.seriesKey &&
        row[DownloadsSchema.colChapterKey] == excludeOpen.id.chapterKey;
  }
}
