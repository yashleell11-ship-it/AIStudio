import 'dart:convert';

import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:sqflite/sqflite.dart';

/// The on-device bookmarks table and its outbox, for exactly one
/// `(user, profile)` scope.
///
/// An extension on [DownloadsStore] rather than a class of its own, and that
/// is the isolation argument: [DownloadsStore.scopeId] is fixed at
/// construction and there is no way to reach these methods except through an
/// instance that already carries a scope, so — exactly like `saved_chapters`
/// and `progress_outbox` — no call site exists that could pass a different
/// one. Every statement below names `scope_id` itself.
///
/// **Reads come from here first.** The Bookmarks screen, and the reader's
/// "which bookmarks are in this chapter", are answered off the device with no
/// network call at all; the server is a peer that is merged in when one is
/// available, never the thing the screen waits on.
extension DownloadsStoreBookmarks on DownloadsStore {
  /// Create or update a bookmark, offline-safe: the row and its outbox op are
  /// written in ONE transaction, so there is no window in which the reader
  /// shows a bookmark that will never be sent, or sends one it does not show.
  ///
  /// Returns the stored row. A tombstoned [Bookmark.clientId] is refused
  /// locally the same way the server refuses it — a tombstone is terminal, and
  /// re-bookmarking mints a new id rather than resurrecting a dead one.
  Future<Bookmark?> saveBookmark(Bookmark bookmark) async {
    final db = await database;
    return db.transaction<Bookmark?>((txn) async {
      final existing = await _rowFor(txn, bookmark.clientId);
      if (existing != null && existing[DownloadsSchema.colDeletedAt] != null) {
        return null;
      }
      // The server row id is not the client's to invent, but it IS the
      // client's to keep: a re-save of an already-synced bookmark must not
      // forget it, or the Bookmarks screen loses its "delete by id" fallback.
      final merged = bookmark.copyWith(
        id: bookmark.id ?? (existing?[DownloadsSchema.colServerId] as int?),
      );
      await txn.insert(
        DownloadsSchema.bookmarks,
        _toRow(merged, scopeId),
        conflictAlgorithm: ConflictAlgorithm.replace,
      );
      await _enqueue(txn, BookmarkOp(op: kBookmarkOpUpsert, bookmark: merged));
      return merged;
    });
  }

  /// Tombstone a bookmark and queue the delete. A no-op for an id this scope
  /// does not hold — a delete of someone else's bookmark is not a delete.
  ///
  /// The row is marked, never removed: a device that is offline when the
  /// delete happens learns about it from the tombstone, and a row that simply
  /// vanished would be indistinguishable from one never pulled.
  Future<bool> tombstoneBookmark(String clientId) async {
    final db = await database;
    return db.transaction<bool>((txn) async {
      final existing = await _rowFor(txn, clientId);
      if (existing == null) return false;
      final stored = _fromRow(existing);
      if (stored.deleted) return false;
      final stamp = DateTime.now().toUtc();
      final tombstone =
          stored.copyWith(deleted: true, deletedAt: stamp, updatedAt: stamp);
      await txn.update(
        DownloadsSchema.bookmarks,
        _toRow(tombstone, scopeId),
        where: '${DownloadsSchema.colScopeId} = ? AND '
            '${DownloadsSchema.colClientId} = ?',
        whereArgs: [scopeId, clientId],
      );
      await _enqueue(
        txn,
        BookmarkOp(op: kBookmarkOpDelete, bookmark: tombstone),
      );
      return true;
    });
  }

  /// Every live bookmark in this scope, most recently changed first — the
  /// Bookmarks screen's list, served with no signal at all.
  Future<List<Bookmark>> listBookmarks() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.bookmarks,
      where: '${DownloadsSchema.colScopeId} = ? AND '
          '${DownloadsSchema.colDeletedAt} IS NULL',
      whereArgs: [scopeId],
      orderBy: '${DownloadsSchema.colUpdatedAt} DESC',
    );
    return rows.map(_fromRow).toList();
  }

  /// The live bookmarks inside one chapter, earliest position first — what
  /// the reader asks for when it opens a chapter.
  Future<List<Bookmark>> chapterBookmarks(ChapterIdentity id) async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.bookmarks,
      where: '${DownloadsSchema.colScopeId} = ? AND '
          '${DownloadsSchema.colSourceId} = ? AND '
          '${DownloadsSchema.colSeriesKey} = ? AND '
          '${DownloadsSchema.colChapterKey} = ? AND '
          '${DownloadsSchema.colDeletedAt} IS NULL',
      whereArgs: [scopeId, id.sourceId, id.seriesKey, id.chapterKey],
      orderBy: '${DownloadsSchema.colAnchorIndex} ASC, '
          '${DownloadsSchema.colAnchorFraction} ASC',
    );
    return rows.map(_fromRow).toList();
  }

  Future<Bookmark?> getBookmark(String clientId) async {
    final db = await database;
    final row = await _rowFor(db, clientId);
    return row == null ? null : _fromRow(row);
  }

  /// Every op still waiting to reach the server, **oldest first**, with the
  /// outbox row id to hand back to [clearBookmarkOutbox] once accepted.
  ///
  /// Ordered by the autoincrement id and not by `created_at`: a create and the
  /// delete that follows it can land in the same millisecond, and replaying
  /// them the other way round would send a delete for a bookmark the server
  /// has never heard of and then create it — resurrecting exactly what the
  /// reader threw away.
  Future<List<(int outboxId, BookmarkOp op)>> pendingBookmarkOutbox() async {
    final db = await database;
    final rows = await db.query(
      DownloadsSchema.bookmarkOutbox,
      where: '${DownloadsSchema.colScopeId} = ?',
      whereArgs: [scopeId],
      orderBy: DownloadsSchema.colId,
    );
    return [
      for (final row in rows)
        (
          row[DownloadsSchema.colId]! as int,
          BookmarkOp.fromJson(
            jsonDecode(row[DownloadsSchema.colPayloadJson]! as String)
                as Map<String, dynamic>,
          ),
        ),
    ];
  }

  Future<void> clearBookmarkOutbox(List<int> outboxIds) async {
    if (outboxIds.isEmpty) return;
    final db = await database;
    final placeholders = List.filled(outboxIds.length, '?').join(',');
    await db.delete(
      DownloadsSchema.bookmarkOutbox,
      where: '${DownloadsSchema.colScopeId} = ? AND '
          '${DownloadsSchema.colId} IN ($placeholders)',
      whereArgs: [scopeId, ...outboxIds],
    );
  }

  /// Record the server row id a flush came back with, so a later delete can
  /// fall back to `DELETE /reader/bookmarks/{id}` if it ever needs to.
  /// Deliberately not a full overwrite: the flush's echo is the server's view
  /// of a row this device just wrote, and adopting it wholesale would undo an
  /// edit made in the seconds since.
  Future<void> adoptServerId(String clientId, int serverId) async {
    final db = await database;
    await db.update(
      DownloadsSchema.bookmarks,
      {DownloadsSchema.colServerId: serverId},
      where: '${DownloadsSchema.colScopeId} = ? AND '
          '${DownloadsSchema.colClientId} = ?',
      whereArgs: [scopeId, clientId],
    );
  }

  /// Fold a server listing into the device's rows.
  ///
  /// The merge is deliberately the SAME rule the server applies to a flush
  /// (`services.bookmark_service.decide`), read from the other side:
  ///
  /// * **A tombstone is terminal, whichever side holds it.** A local delete
  ///   that has not flushed yet must not be undone by the server still
  ///   listing the bookmark as live, and a server tombstone must survive a
  ///   local row that looks newer.
  /// * **Unknown ids are inserted**, tombstones included, so a delete made on
  ///   the web is *learned* rather than inferred from an absence.
  /// * **Otherwise last-write-wins** on `updated_at`, ties going to the local
  ///   row — a device that has an unflushed edit keeps it, and the next flush
  ///   is what settles the disagreement.
  ///
  /// Rows absent from [remote] are left alone: a listing is one page of one
  /// query, and treating absence as deletion would empty the screen the first
  /// time the response was short.
  ///
  /// Returns how many device rows it actually wrote, so a caller can skip
  /// re-reading (and re-rendering) a list the server had nothing new to say
  /// about — which is the common case on every launch after the first.
  Future<int> mergeServerBookmarks(List<Bookmark> remote) async {
    if (remote.isEmpty) return 0;
    final db = await database;
    var written = 0;
    await db.transaction((txn) async {
      for (final incoming in remote) {
        final existing = await _rowFor(txn, incoming.clientId);
        if (existing == null) {
          await txn.insert(
            DownloadsSchema.bookmarks,
            _toRow(incoming, scopeId),
            conflictAlgorithm: ConflictAlgorithm.replace,
          );
          written++;
          continue;
        }
        final local = _fromRow(existing);
        if (local.deleted) {
          // Terminal. Only the server's row id is worth taking.
          if (local.id == null && incoming.id != null) {
            await txn.update(
              DownloadsSchema.bookmarks,
              {DownloadsSchema.colServerId: incoming.id},
              where: '${DownloadsSchema.colScopeId} = ? AND '
                  '${DownloadsSchema.colClientId} = ?',
              whereArgs: [scopeId, incoming.clientId],
            );
            written++;
          }
          continue;
        }
        if (!incoming.deleted &&
            !incoming.updatedAt.isAfter(local.updatedAt)) {
          continue;
        }
        await txn.insert(
          DownloadsSchema.bookmarks,
          _toRow(incoming, scopeId),
          conflictAlgorithm: ConflictAlgorithm.replace,
        );
        written++;
      }
    });
    return written;
  }

  Future<void> _enqueue(DatabaseExecutor txn, BookmarkOp op) =>
      txn.insert(DownloadsSchema.bookmarkOutbox, {
        DownloadsSchema.colScopeId: scopeId,
        DownloadsSchema.colClientId: op.bookmark.clientId,
        DownloadsSchema.colPayloadJson: jsonEncode(op.toJson()),
        DownloadsSchema.colCreatedAt:
            DateTime.now().toUtc().toIso8601String(),
      });

  Future<Map<String, Object?>?> _rowFor(
    DatabaseExecutor db,
    String clientId,
  ) async {
    final rows = await db.query(
      DownloadsSchema.bookmarks,
      where: '${DownloadsSchema.colScopeId} = ? AND '
          '${DownloadsSchema.colClientId} = ?',
      whereArgs: [scopeId, clientId],
      limit: 1,
    );
    return rows.isEmpty ? null : rows.first;
  }
}

Map<String, Object?> _toRow(Bookmark bookmark, String scopeId) => {
      DownloadsSchema.colScopeId: scopeId,
      DownloadsSchema.colClientId: bookmark.clientId,
      DownloadsSchema.colServerId: bookmark.id,
      DownloadsSchema.colSourceId: bookmark.sourceId,
      DownloadsSchema.colSeriesKey: bookmark.seriesKey,
      DownloadsSchema.colChapterKey: bookmark.chapterKey,
      DownloadsSchema.colSeriesTitle: bookmark.seriesTitle,
      DownloadsSchema.colChapterNumber: bookmark.chapterNumber,
      DownloadsSchema.colMediaType: bookmark.mediaType.wire,
      DownloadsSchema.colAnchorIndex: bookmark.anchorIndex,
      DownloadsSchema.colAnchorFraction: bookmark.anchorFraction,
      DownloadsSchema.colAnchorTotal: bookmark.anchorTotal,
      DownloadsSchema.colSnippet: bookmark.snippet,
      DownloadsSchema.colNote: bookmark.note,
      DownloadsSchema.colCreatedAt: bookmark.createdAt.toUtc().toIso8601String(),
      DownloadsSchema.colUpdatedAt: bookmark.updatedAt.toUtc().toIso8601String(),
      DownloadsSchema.colDeletedAt:
          bookmark.deletedAt?.toUtc().toIso8601String(),
    };

Bookmark _fromRow(Map<String, Object?> row) {
  final deletedAt = bookmarkInstant(row[DownloadsSchema.colDeletedAt]);
  return Bookmark(
    id: row[DownloadsSchema.colServerId] as int?,
    clientId: row[DownloadsSchema.colClientId]! as String,
    sourceId: row[DownloadsSchema.colSourceId]! as String,
    seriesKey: row[DownloadsSchema.colSeriesKey]! as String,
    chapterKey: row[DownloadsSchema.colChapterKey]! as String,
    seriesTitle: row[DownloadsSchema.colSeriesTitle] as String?,
    chapterNumber: (row[DownloadsSchema.colChapterNumber] as num?)?.toDouble(),
    mediaType: BookmarkMedia.fromWire(
      row[DownloadsSchema.colMediaType] as String?,
    ),
    anchorIndex: (row[DownloadsSchema.colAnchorIndex] as num?)?.toInt() ?? 1,
    anchorFraction:
        (row[DownloadsSchema.colAnchorFraction] as num?)?.toDouble() ?? 0,
    anchorTotal: (row[DownloadsSchema.colAnchorTotal] as num?)?.toInt() ?? 0,
    snippet: row[DownloadsSchema.colSnippet] as String?,
    note: row[DownloadsSchema.colNote] as String?,
    deleted: deletedAt != null,
    createdAt: bookmarkInstant(row[DownloadsSchema.colCreatedAt]) ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    updatedAt: bookmarkInstant(row[DownloadsSchema.colUpdatedAt]) ??
        DateTime.fromMillisecondsSinceEpoch(0, isUtc: true),
    deletedAt: deletedAt,
  );
}
