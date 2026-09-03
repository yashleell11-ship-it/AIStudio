import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:sqflite/sqflite.dart';

/// Deletes one chapter's on-device bytes: decrements/removes its blob
/// refcounts (freeing the file only once the last referencing profile has
/// let go of it), removes its `saved_pages` rows, then removes the
/// `saved_chapters` row itself.
///
/// **Why the chapter row is deleted outright rather than kept as a
/// "not downloaded" stub:** reading progress (last page, completed, time
/// spent) lives entirely in the separate server-synced progress system
/// (`POST /reader/progress[/batch]` + the local outbox) — it was never
/// stored here. So removing this row loses exactly one thing: the local
/// bookkeeping this table exists to hold (download state, on-device bytes,
/// the pin flag, the read-then-expire timer). The chapter goes back to "on
/// server, not on phone", never to "never read" — the read history that
/// would make it look unread lives elsewhere and is untouched.
///
/// Shared by [DownloadsStore.deleteDownload] (single scope, user-invoked —
/// "remove this download") and `RetentionMaintenance` (cross-scope,
/// automatic — the read-then-expire sweep and cap eviction), so the two
/// paths can never disagree about what "delete a chapter" means.
Future<int> deleteChapterAndBlobs({
  required Database db,
  required BlobStore blobStore,
  required int chapterRowId,
  required String scopeId,
}) async {
  final hashesToMaybeDelete = <String>{};
  var freedBytes = 0;

  await db.transaction((txn) async {
    final pages = await txn.query(
      DownloadsSchema.savedPages,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colChapterRowId} = ?',
      whereArgs: [scopeId, chapterRowId],
    );

    for (final page in pages) {
      final hash = page[DownloadsSchema.colBlobHash]! as String;
      final size = page[DownloadsSchema.colSize]! as int;
      freedBytes += size;

      await txn.rawUpdate(
        'UPDATE ${DownloadsSchema.blobs} SET ${DownloadsSchema.colRefcount} = ${DownloadsSchema.colRefcount} - 1 '
        'WHERE ${DownloadsSchema.colHash} = ?',
        [hash],
      );
      final refRows = await txn.query(
        DownloadsSchema.blobs,
        columns: [DownloadsSchema.colRefcount],
        where: '${DownloadsSchema.colHash} = ?',
        whereArgs: [hash],
      );
      final refcount = refRows.isEmpty
          ? 0
          : (refRows.first[DownloadsSchema.colRefcount]! as int);
      if (refcount <= 0) {
        await txn.delete(
          DownloadsSchema.blobs,
          where: '${DownloadsSchema.colHash} = ?',
          whereArgs: [hash],
        );
        hashesToMaybeDelete.add(hash);
      }
    }

    await txn.delete(
      DownloadsSchema.savedPages,
      where: '${DownloadsSchema.colScopeId} = ? AND ${DownloadsSchema.colChapterRowId} = ?',
      whereArgs: [scopeId, chapterRowId],
    );
    await txn.delete(
      DownloadsSchema.savedChapters,
      where: '${DownloadsSchema.colId} = ?',
      whereArgs: [chapterRowId],
    );
  });

  // File deletion happens after the transaction commits — an orphaned file
  // from a crash between commit and delete is recoverable (BlobStore.write
  // treats "already on disk" as success); a file deleted before the
  // transaction commits, on a commit that then rolled back, would not be.
  for (final hash in hashesToMaybeDelete) {
    await blobStore.delete(hash);
  }

  return freedBytes;
}
