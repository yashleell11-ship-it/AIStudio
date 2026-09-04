import 'dart:convert';
import 'dart:io';

import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/models/series_storage_usage.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_deletion.dart';
import 'package:manhwamaniacs/features/reader/models/reading_progress.dart';
import 'package:sqflite/sqflite.dart';

/// The on-device chapter store for exactly one `(user, profile)` scope.
///
/// **Isolation is structural, not conventional.** [scopeId] is fixed at
/// construction and every query below adds `WHERE scope_id = ?scopeId`
/// itself — there is no method on this class that accepts a caller-supplied
/// scope, so there is no call site that could pass the wrong one. The
/// [DownloadsStore] provider (`providers/downloads_scope.dart`) returns
/// `null` — no instance at all — when either half of the scope is missing,
/// so a screen with no resolvable store renders "nothing downloaded" rather
/// than falling back to some default scope.
///
/// The one exception is [blobs]: content-addressed and refcounted *across*
/// scopes on purpose, so two profiles downloading the same chapter store one
/// copy. A blob's bytes carry no per-profile information — only the
/// `saved_pages` row that references it does, and that row is scoped.
class DownloadsStore {
  DownloadsStore({
    required this.scopeId,
    required this.database,
    required this.blobStore,
  });

  final String scopeId;
  final Future<Database> database;
  final Future<BlobStore> blobStore;

  // ── Queueing ───────────────────────────────────────────────────────────

  /// Ensures a chapter has a row in this scope, in the [DownloadChapterState.queued]
  /// state, ready for the queue engine to pick up. Idempotent:
  ///
  /// - Already `queued`/`downloading`/`complete` → left untouched, so a
  ///   double-tap on "Download" never restarts an in-flight fetch or
  ///   re-queues a finished chapter.
  /// - `failed` → reset to `queued` with `retry_count` and `error` cleared —
  ///   this is also what a manual "Retry" tap calls.
  ///
  /// Returns the row id.
  Future<int> ensureQueued({
    required ChapterIdentity id,
    double? chapterNumber,
    String? title,
    String? seriesTitle,
  }) async {
    final db = await database;
    final existing = await _getRow(db, id);
    if (existing != null) {
      final state = DownloadChapterState.fromWire(
        existing[DownloadsSchema.colState]! as String,
      );
      if (state == DownloadChapterState.failed) {
        await db.update(
          DownloadsSchema.savedChapters,
          {
            DownloadsSchema.colState: DownloadChapterState.queued.wire,
            DownloadsSchema.colRetryCount: 0,
            DownloadsSchema.colError: null,
          },
          where: '${DownloadsSchema.colId} = ?',
          whereArgs: [existing[DownloadsSchema.colId]],
        );
      }
      return existing[DownloadsSchema.colId]! as int;
    }

    return db.insert(DownloadsSchema.savedChapters, {
      DownloadsSchema.colScopeId: scopeId,
      DownloadsSchema.colSourceId: id.sourceId,
      DownloadsSchema.colSeriesKey: id.seriesKey,
      DownloadsSchema.colChapterKey: id.chapterKey,
      DownloadsSchema.colChapterNumber: chapterNumber,
      DownloadsSchema.colTitle: title,
      DownloadsSchema.colSeriesTitle: seriesTitle,
      DownloadsSchema.colPageCount: 0,
      DownloadsSchema.colBytes: 0,
      DownloadsSchema.colState: DownloadChapterState.queued.wire,
      DownloadsSchema.colPinned: 0,
      DownloadsSchema.colReadAt: null,
      DownloadsSchema.colCreatedAt: DateTime.now().toUtc().toIso8601String(),
      DownloadsSchema.colRetryCount: 0,
      DownloadsSchema.colError: null,
    });
  }

  /// Chapters waiting for or mid-download, oldest first — the durable queue.
  /// Re-read on every app launch so a kill mid-download resumes rather than
  /// vanishing.
  Future<List<SavedChapter>> pendingChapters() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.savedChapters,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colState} IN (?, ?)',
      whereArgs: [
        scopeId,
        DownloadChapterState.queued.wire,
        DownloadChapterState.downloading.wire,
      ],
      orderBy: DownloadsSchema.colCreatedAt,
    );
    return rows.map(SavedChapter.fromRow).toList();
  }

  /// Everything the queue still owes the user — queued, mid-download **and**
  /// failed — oldest first, i.e. exactly what the Downloads screen's queue
  /// panel lists and what its badge counts.
  ///
  /// Deliberately wider than [pendingChapters] (which drives the engine and
  /// must never re-pick a chapter that exhausted its retries): a failed
  /// chapter is not work the queue will do on its own, but it is absolutely
  /// still something the user is waiting on and can retry.
  Future<List<SavedChapter>> unfinishedChapters() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.savedChapters,
      where:
          '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colState} IN (?, ?, ?)',
      whereArgs: [
        scopeId,
        DownloadChapterState.queued.wire,
        DownloadChapterState.downloading.wire,
        DownloadChapterState.failed.wire,
      ],
      orderBy: DownloadsSchema.colCreatedAt,
    );
    return rows.map(SavedChapter.fromRow).toList();
  }

  Future<void> updateManifestInfo({
    required int rowId,
    required int pageCount,
    double? chapterNumber,
    String? title,
    String? seriesTitle,
  }) async {
    final db = await database;
    await db.update(
      DownloadsSchema.savedChapters,
      {
        DownloadsSchema.colPageCount: pageCount,
        DownloadsSchema.colState: DownloadChapterState.downloading.wire,
        if (chapterNumber != null) DownloadsSchema.colChapterNumber: chapterNumber,
        if (title != null) DownloadsSchema.colTitle: title,
        if (seriesTitle != null) DownloadsSchema.colSeriesTitle: seriesTitle,
      },
      where: '${DownloadsSchema.colId} = ?',
      whereArgs: [rowId],
    );
  }

  /// Page numbers already saved for this chapter — the resume check. Fetching
  /// a manifest again after a kill is cheap; re-fetching pages already on
  /// disk is not, so the queue engine skips every number in this set.
  Future<Set<int>> existingPageNumbers(int rowId) async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.savedPages,
      columns: [DownloadsSchema.colPageNumber],
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colChapterRowId} = ?',
      whereArgs: [scopeId, rowId],
    );
    return rows.map((r) => r[DownloadsSchema.colPageNumber]! as int).toSet();
  }

  /// Writes one page's bytes to the blob tree and records it against
  /// [rowId]. Safe to call twice for the same page (e.g. a retry racing a
  /// resume) — the second call is a no-op for both the blob refcount and the
  /// chapter's byte total.
  Future<void> savePage({
    required int rowId,
    required int pageNumber,
    required List<int> bytes,
  }) async {
    final blob = await blobStore;
    final written = await blob.write(bytes);
    final db = await database;
    await db.transaction((txn) async {
      final pageInserted = await txn.insert(
        DownloadsSchema.savedPages,
        {
          DownloadsSchema.colScopeId: scopeId,
          DownloadsSchema.colChapterRowId: rowId,
          DownloadsSchema.colPageNumber: pageNumber,
          DownloadsSchema.colBlobHash: written.hash,
          DownloadsSchema.colSize: written.size,
        },
        conflictAlgorithm: ConflictAlgorithm.ignore,
      );
      // insert() returns the new rowid, but ConflictAlgorithm.ignore returns
      // 0 on a no-op conflict — sqflite's documented way to detect it.
      if (pageInserted == 0) return;

      final blobRow = await txn.query(
        DownloadsSchema.blobs,
        where: '${DownloadsSchema.colHash} = ?',
        whereArgs: [written.hash],
      );
      if (blobRow.isEmpty) {
        await txn.insert(DownloadsSchema.blobs, {
          DownloadsSchema.colHash: written.hash,
          DownloadsSchema.colRefcount: 1,
          DownloadsSchema.colSize: written.size,
        });
      } else {
        await txn.rawUpdate(
          'UPDATE ${DownloadsSchema.blobs} SET ${DownloadsSchema.colRefcount} = ${DownloadsSchema.colRefcount} + 1 '
          'WHERE ${DownloadsSchema.colHash} = ?',
          [written.hash],
        );
      }

      await txn.rawUpdate(
        'UPDATE ${DownloadsSchema.savedChapters} SET ${DownloadsSchema.colBytes} = ${DownloadsSchema.colBytes} + ? '
        'WHERE ${DownloadsSchema.colId} = ?',
        [written.size, rowId],
      );
    });
  }

  /// Marks the chapter complete **only if** every page is actually present —
  /// the one guard standing between a race in the queue engine and a chapter
  /// that claims to be downloaded but isn't. Returns whether it did.
  Future<bool> markCompleteIfAllPagesPresent(int rowId) async {
    final db = await database;
    final chapterRows = await db.query(
      DownloadsSchema.savedChapters,
      where: '${DownloadsSchema.colId} = ?',
      whereArgs: [rowId],
    );
    if (chapterRows.isEmpty) return false;
    final pageCount = chapterRows.first[DownloadsSchema.colPageCount]! as int;
    if (pageCount <= 0) return false;

    final countResult = await db.rawQuery(
      'SELECT COUNT(*) AS n FROM ${DownloadsSchema.savedPages} '
      'WHERE ${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colChapterRowId} = ?',
      [scopeId, rowId],
    );
    final present = Sqflite.firstIntValue(countResult) ?? 0;
    if (present < pageCount) return false;

    await db.update(
      DownloadsSchema.savedChapters,
      {DownloadsSchema.colState: DownloadChapterState.complete.wire, DownloadsSchema.colError: null},
      where: '${DownloadsSchema.colId} = ?',
      whereArgs: [rowId],
    );
    return true;
  }

  Future<void> incrementRetry(int rowId) async {
    final db = await database;
    await db.rawUpdate(
      'UPDATE ${DownloadsSchema.savedChapters} SET ${DownloadsSchema.colRetryCount} = ${DownloadsSchema.colRetryCount} + 1 '
      'WHERE ${DownloadsSchema.colId} = ?',
      [rowId],
    );
  }

  Future<void> markFailed({required int rowId, required String error}) async {
    final db = await database;
    await db.update(
      DownloadsSchema.savedChapters,
      {DownloadsSchema.colState: DownloadChapterState.failed.wire, DownloadsSchema.colError: error},
      where: '${DownloadsSchema.colId} = ?',
      whereArgs: [rowId],
    );
  }

  // ── Reading ────────────────────────────────────────────────────────────

  Future<SavedChapter?> getChapter(ChapterIdentity id) async {
    final db = await database;
    final row = await _getRow(db, id);
    return row == null ? null : SavedChapter.fromRow(row);
  }

  /// True when [id] is fully downloaded in this scope and every one of its
  /// blob files still exists on disk (a user can delete files by hand
  /// through the Files app — this is how that shows up as "not actually
  /// available" instead of serving a broken image).
  Future<bool> isAvailableOffline(ChapterIdentity id) async {
    final chapter = await getChapter(id);
    if (chapter == null || chapter.state != DownloadChapterState.complete) {
      return false;
    }
    final paths = await localPagePaths(id);
    return paths.length == chapter.pageCount &&
        paths.values.every((f) => f.existsSync() && f.lengthSync() > 0);
  }

  /// Absolute on-disk paths for every page of [id] currently present in this
  /// scope, keyed by page number. Only includes pages whose blob file still
  /// exists — an orphaned index row (file deleted by hand) is silently
  /// skipped so callers fall back to network for just that page.
  Future<Map<int, File>> localPagePaths(ChapterIdentity id) async {
    final db = await database;
    final chapterRow = await _getRow(db, id);
    if (chapterRow == null) return {};
    final rowId = chapterRow[DownloadsSchema.colId]! as int;

    final rows = await db.query(
      DownloadsSchema.savedPages,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colChapterRowId} = ?',
      whereArgs: [scopeId, rowId],
    );

    final blob = await blobStore;
    final result = <int, File>{};
    for (final row in rows) {
      final hash = row[DownloadsSchema.colBlobHash]! as String;
      final file = blob.pathFor(hash);
      if (file.existsSync() && file.lengthSync() > 0) {
        result[row[DownloadsSchema.colPageNumber]! as int] = file;
      }
    }
    return result;
  }

  Future<List<SavedChapter>> listChapters() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.savedChapters,
      where: '${DownloadsSchema.colScopeId} = ?',
      whereArgs: [scopeId],
      orderBy: '${DownloadsSchema.colCreatedAt} DESC',
    );
    return rows.map(SavedChapter.fromRow).toList();
  }

  Future<List<SeriesStorageUsage>> seriesBreakdown() async {
    final db = await database;
    final rows = await db.rawQuery(
      '''
      SELECT ${DownloadsSchema.colSourceId}, ${DownloadsSchema.colSeriesKey},
             MAX(${DownloadsSchema.colSeriesTitle}) AS series_title,
             SUM(${DownloadsSchema.colBytes}) AS total_bytes,
             COUNT(*) AS chapter_count,
             SUM(${DownloadsSchema.colPinned}) AS pinned_count
      FROM ${DownloadsSchema.savedChapters}
      WHERE ${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colState} = ?
      GROUP BY ${DownloadsSchema.colSourceId}, ${DownloadsSchema.colSeriesKey}
      ORDER BY total_bytes DESC
      ''',
      [scopeId, DownloadChapterState.complete.wire],
    );
    return rows
        .map(
          (row) => SeriesStorageUsage(
            sourceId: row[DownloadsSchema.colSourceId]! as String,
            seriesKey: row[DownloadsSchema.colSeriesKey]! as String,
            seriesTitle: row['series_title'] as String?,
            bytes: (row['total_bytes'] as num?)?.toInt() ?? 0,
            chapterCount: (row['chapter_count'] as num?)?.toInt() ?? 0,
            pinnedChapterCount: (row['pinned_count'] as num?)?.toInt() ?? 0,
          ),
        )
        .toList();
  }

  /// This scope's own nominal total (sum of each complete chapter's byte
  /// count). Cross-profile dedup means the *actual* disk usage can be lower
  /// than the sum of every profile's totals — see
  /// `RetentionMaintenance.totalDeviceBytes` for the real figure the cap
  /// enforces against.
  Future<int> scopeBytes() async {
    final db = await database;
    final result = await db.rawQuery(
      'SELECT SUM(${DownloadsSchema.colBytes}) AS total FROM ${DownloadsSchema.savedChapters} '
      'WHERE ${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colState} = ?',
      [scopeId, DownloadChapterState.complete.wire],
    );
    return (result.first['total'] as num?)?.toInt() ?? 0;
  }

  // ── Pin / read state ───────────────────────────────────────────────────

  Future<void> setSeriesPinned({
    required SeriesIdentity series,
    required bool pinned,
  }) async {
    final db = await database;
    await db.update(
      DownloadsSchema.savedChapters,
      {DownloadsSchema.colPinned: pinned ? 1 : 0},
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colSourceId} = ? AND ${DownloadsSchema.colSeriesKey} = ?',
      whereArgs: [scopeId, series.sourceId, series.seriesKey],
    );
  }

  /// Stamps `read_at` — call when a downloaded chapter reaches
  /// `read_complete`. A no-op when [id] has no row in this scope (the
  /// chapter was never downloaded, so there is nothing to expire).
  Future<void> markRead(ChapterIdentity id) async {
    // Best-effort local bookkeeping, called fire-and-forget from reader
    // completion — a platform-channel hiccup here must never surface as an
    // unhandled error in the reader.
    try {
      final db = await database;
      await db.update(
        DownloadsSchema.savedChapters,
        {DownloadsSchema.colReadAt: DateTime.now().toUtc().toIso8601String()},
        where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colSourceId} = ? AND '
            '${DownloadsSchema.colSeriesKey} = ? AND ${DownloadsSchema.colChapterKey} = ?',
        whereArgs: [scopeId, id.sourceId, id.seriesKey, id.chapterKey],
      );
    } catch (_) {
      // Retried next time this chapter reaches read_complete.
    }
  }

  /// Clears `read_at` — call when a downloaded chapter is re-opened, so a
  /// deliberate re-read is never deleted out from under the reader.
  Future<void> clearReadStamp(ChapterIdentity id) async {
    // Best-effort local bookkeeping, called fire-and-forget on chapter open
    // (see OpenChapterScope) — must never surface as an unhandled error.
    try {
      final db = await database;
      await db.update(
        DownloadsSchema.savedChapters,
        {DownloadsSchema.colReadAt: null},
        where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colSourceId} = ? AND '
            '${DownloadsSchema.colSeriesKey} = ? AND ${DownloadsSchema.colChapterKey} = ?',
        whereArgs: [scopeId, id.sourceId, id.seriesKey, id.chapterKey],
      );
    } catch (_) {
      // If the read-then-expire sweep beats a retry to it, the chapter is
      // simply re-downloaded — never a data-loss failure mode.
    }
  }

  /// Removes [id]'s on-device bytes from this scope — the user-facing
  /// "Remove download" action. Progress and read history survive (see
  /// [deleteChapterAndBlobs]); a no-op if [id] has no row in this scope.
  Future<void> deleteDownload(ChapterIdentity id) async {
    final db = await database;
    final row = await _getRow(db, id);
    if (row == null) return;
    await deleteChapterAndBlobs(
      db: db,
      blobStore: await blobStore,
      chapterRowId: row[DownloadsSchema.colId]! as int,
      scopeId: scopeId,
    );
  }

  // ── Progress outbox ────────────────────────────────────────────────────
  //
  // Every reader progress save writes here first — the reader must never
  // block on (or lose a save to) a flaky connection. `flushProgressOutbox`
  // (`services/progress_outbox.dart`) drains this on connectivity/app-resume
  // via `POST /reader/progress/batch`; the server's furthest-wins merge
  // makes replaying an already-flushed push harmless, so a crash between a
  // successful POST and this row's deletion self-heals on the next flush.

  Future<void> enqueueProgress(ProgressPush push) async {
    final db = await database;
    await db.insert(DownloadsSchema.progressOutbox, {
      DownloadsSchema.colScopeId: scopeId,
      DownloadsSchema.colPayloadJson: jsonEncode(push.toJson()),
      DownloadsSchema.colCreatedAt: DateTime.now().toUtc().toIso8601String(),
    });
  }

  /// Every push still waiting to reach the server, oldest first, alongside
  /// the outbox row id a caller must pass back to [clearProgressOutbox] once
  /// it has actually been accepted.
  Future<List<(int outboxId, ProgressPush push)>> pendingProgressOutbox() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.progressOutbox,
      where: '${DownloadsSchema.colScopeId} = ?',
      whereArgs: [scopeId],
      orderBy: DownloadsSchema.colCreatedAt,
    );
    return [
      for (final row in rows)
        (
          row[DownloadsSchema.colId]! as int,
          ProgressPush.fromJson(
            jsonDecode(row[DownloadsSchema.colPayloadJson]! as String)
                as Map<String, dynamic>,
          ),
        ),
    ];
  }

  Future<void> clearProgressOutbox(List<int> outboxIds) async {
    if (outboxIds.isEmpty) return;
    final db = await database;
    final placeholders = List.filled(outboxIds.length, '?').join(',');
    await db.delete(
      DownloadsSchema.progressOutbox,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colId} IN ($placeholders)',
      whereArgs: [scopeId, ...outboxIds],
    );
  }

  Future<Map<String, Object?>?> _getRow(Database db, ChapterIdentity id) async {
    final rows = await db.query(
      DownloadsSchema.savedChapters,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colSourceId} = ? AND '
          '${DownloadsSchema.colSeriesKey} = ? AND ${DownloadsSchema.colChapterKey} = ?',
      whereArgs: [scopeId, id.sourceId, id.seriesKey, id.chapterKey],
    );
    return rows.isEmpty ? null : rows.first;
  }
}
