import 'dart:io';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';

/// Table/column names as bare constants — every query in [DownloadsStore]
/// goes through these instead of inline string literals, so a rename is a
/// one-file change.
abstract final class DownloadsSchema {
  static const savedChapters = 'saved_chapters';
  static const savedPages = 'saved_pages';
  static const blobs = 'blobs';
  static const progressOutbox = 'progress_outbox';

  static const colId = 'id';
  static const colScopeId = 'scope_id';
  static const colSourceId = 'source_id';
  static const colSeriesKey = 'series_key';
  static const colChapterKey = 'chapter_key';
  static const colChapterNumber = 'chapter_number';
  static const colTitle = 'title';
  static const colSeriesTitle = 'series_title';
  static const colPageCount = 'page_count';
  static const colBytes = 'bytes';
  static const colState = 'state';
  static const colPinned = 'pinned';
  static const colReadAt = 'read_at';
  static const colCreatedAt = 'created_at';
  static const colRetryCount = 'retry_count';
  static const colError = 'error';

  /// What the saved blobs hold: `'manga'` (one blob per page image) or
  /// `'novel'` (one blob of paragraph JSON for the whole chapter). Added in
  /// schema v2; every pre-existing row is manga, which is what the column
  /// default says.
  static const colKind = 'kind';

  static const colChapterRowId = 'chapter_rowid';
  static const colPageNumber = 'page_number';
  static const colBlobHash = 'blob_hash';
  static const colSize = 'size';

  static const colHash = 'hash';
  static const colRefcount = 'refcount';

  static const colPayloadJson = 'payload_json';
}

const _dbVersion = 2;

/// The `kind` column's two values. A row's own kind, not a lookup through the
/// sources listing — the offline path has no listing, and a downloaded
/// chapter must be readable on a plane.
const String kMangaDownloadKind = 'manga';
const String kNovelDownloadKind = 'novel';

/// The on-device store's database file name, under
/// `getApplicationSupportDirectory()` — deliberately **not**
/// `getApplicationDocumentsDirectory()` (that's reserved for blob bytes so
/// the Files app can surface them, spec §3b) and never
/// `getTemporaryDirectory()` (iOS purges it under pressure).
///
/// Kept separate from the blob tree on purpose: a user who deletes files by
/// hand from the Files app can only ever orphan a blob (recoverable — the
/// index still knows what *should* be there), never half-delete this index
/// (not recoverable).
Future<Database> openDownloadsDatabase({String? overridePath}) async {
  final path = overridePath ?? await _defaultDbPath();
  return openDatabase(
    path,
    version: _dbVersion,
    onUpgrade: (db, oldVersion, newVersion) async {
      // v1 → v2: novels. `ADD COLUMN` with a default is the one schema change
      // SQLite performs without rewriting the table, so an install with
      // thousands of downloaded chapters upgrades instantly — and every row
      // that already exists is a manga chapter, which is exactly what the
      // default backfills.
      if (oldVersion < 2) {
        await db.execute(
          'ALTER TABLE ${DownloadsSchema.savedChapters} '
          'ADD COLUMN ${DownloadsSchema.colKind} TEXT NOT NULL '
          "DEFAULT '$kMangaDownloadKind'",
        );
      }
    },
    onCreate: (db, version) async {
      await db.execute('''
        CREATE TABLE ${DownloadsSchema.savedChapters} (
          ${DownloadsSchema.colId} INTEGER PRIMARY KEY AUTOINCREMENT,
          ${DownloadsSchema.colScopeId} TEXT NOT NULL,
          ${DownloadsSchema.colSourceId} TEXT NOT NULL,
          ${DownloadsSchema.colSeriesKey} TEXT NOT NULL,
          ${DownloadsSchema.colChapterKey} TEXT NOT NULL,
          ${DownloadsSchema.colChapterNumber} REAL,
          ${DownloadsSchema.colTitle} TEXT,
          ${DownloadsSchema.colSeriesTitle} TEXT,
          ${DownloadsSchema.colPageCount} INTEGER NOT NULL DEFAULT 0,
          ${DownloadsSchema.colBytes} INTEGER NOT NULL DEFAULT 0,
          ${DownloadsSchema.colState} TEXT NOT NULL,
          ${DownloadsSchema.colPinned} INTEGER NOT NULL DEFAULT 0,
          ${DownloadsSchema.colReadAt} TEXT,
          ${DownloadsSchema.colCreatedAt} TEXT NOT NULL,
          ${DownloadsSchema.colRetryCount} INTEGER NOT NULL DEFAULT 0,
          ${DownloadsSchema.colError} TEXT,
          ${DownloadsSchema.colKind} TEXT NOT NULL DEFAULT '$kMangaDownloadKind',
          UNIQUE(
            ${DownloadsSchema.colScopeId},
            ${DownloadsSchema.colSourceId},
            ${DownloadsSchema.colSeriesKey},
            ${DownloadsSchema.colChapterKey}
          )
        )
      ''');
      await db.execute('''
        CREATE TABLE ${DownloadsSchema.savedPages} (
          ${DownloadsSchema.colScopeId} TEXT NOT NULL,
          ${DownloadsSchema.colChapterRowId} INTEGER NOT NULL,
          ${DownloadsSchema.colPageNumber} INTEGER NOT NULL,
          ${DownloadsSchema.colBlobHash} TEXT NOT NULL,
          ${DownloadsSchema.colSize} INTEGER NOT NULL,
          PRIMARY KEY (
            ${DownloadsSchema.colScopeId},
            ${DownloadsSchema.colChapterRowId},
            ${DownloadsSchema.colPageNumber}
          )
        )
      ''');
      await db.execute('''
        CREATE TABLE ${DownloadsSchema.blobs} (
          ${DownloadsSchema.colHash} TEXT PRIMARY KEY,
          ${DownloadsSchema.colRefcount} INTEGER NOT NULL DEFAULT 0,
          ${DownloadsSchema.colSize} INTEGER NOT NULL
        )
      ''');
      await db.execute('''
        CREATE TABLE ${DownloadsSchema.progressOutbox} (
          ${DownloadsSchema.colId} INTEGER PRIMARY KEY AUTOINCREMENT,
          ${DownloadsSchema.colScopeId} TEXT NOT NULL,
          ${DownloadsSchema.colPayloadJson} TEXT NOT NULL,
          ${DownloadsSchema.colCreatedAt} TEXT NOT NULL
        )
      ''');
      await db.execute(
        'CREATE INDEX idx_saved_pages_chapter '
        'ON ${DownloadsSchema.savedPages}(${DownloadsSchema.colScopeId}, ${DownloadsSchema.colChapterRowId})',
      );
      await db.execute(
        'CREATE INDEX idx_progress_outbox_scope '
        'ON ${DownloadsSchema.progressOutbox}(${DownloadsSchema.colScopeId})',
      );
    },
  );
}

Future<String> _defaultDbPath() async {
  final dir = await getApplicationSupportDirectory();
  final storeDir = Directory(p.join(dir.path, 'mm-store'));
  if (!storeDir.existsSync()) storeDir.createSync(recursive: true);
  return p.join(storeDir.path, 'downloads.db');
}
