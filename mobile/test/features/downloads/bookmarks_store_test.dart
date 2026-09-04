import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/store/bookmarks_dao.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/reader/models/bookmark.dart';
import 'package:sqflite/sqflite.dart';

import '../../support/downloads_test_support.dart';

Bookmark _bookmark({
  String clientId = 'c1',
  String chapterKey = '14',
  int index = 7,
  double fraction = 0.62,
  int total = 11,
  BookmarkMedia media = BookmarkMedia.manga,
  String? snippet,
  int? id,
  DateTime? updatedAt,
  bool deleted = false,
}) {
  final stamp = updatedAt ?? DateTime.utc(2026, 9, 5, 10);
  return Bookmark(
    id: id,
    clientId: clientId,
    sourceId: 'asurascans',
    seriesKey: 'solo-leveling',
    chapterKey: chapterKey,
    chapterNumber: 14,
    mediaType: media,
    anchorIndex: index,
    anchorFraction: fraction,
    anchorTotal: total,
    snippet: snippet,
    createdAt: DateTime.utc(2026, 9, 5, 9),
    updatedAt: stamp,
    deleted: deleted,
    deletedAt: deleted ? stamp : null,
  );
}

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async => harness.dispose());

  group('scope isolation', () {
    test("one profile's bookmarks are invisible to another", () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');

      await storeA.saveBookmark(_bookmark());

      expect(await storeA.listBookmarks(), hasLength(1));
      expect(await storeB.listBookmarks(), isEmpty);
      expect(await storeB.getBookmark('c1'), isNull);
    });

    test('the same client id in two profiles is two independent rows',
        () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');

      await storeA.saveBookmark(_bookmark(index: 3));
      await storeB.saveBookmark(_bookmark(index: 9));

      expect((await storeA.getBookmark('c1'))!.anchorIndex, 3);
      expect((await storeB.getBookmark('c1'))!.anchorIndex, 9);

      // A's delete must not reach into B's row, even though the primary key's
      // second column is identical.
      await storeA.tombstoneBookmark('c1');
      expect((await storeA.getBookmark('c1'))!.deleted, isTrue);
      expect((await storeB.getBookmark('c1'))!.deleted, isFalse);
      expect(await storeB.listBookmarks(), hasLength(1));
    });

    test('outbox rows are scoped too', () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');

      await storeA.saveBookmark(_bookmark());

      expect(await storeA.pendingBookmarkOutbox(), hasLength(1));
      expect(await storeB.pendingBookmarkOutbox(), isEmpty);

      // Clearing by id cannot cross scopes even if the ids ever collided.
      final pendingA = await storeA.pendingBookmarkOutbox();
      await storeB.clearBookmarkOutbox([pendingA.single.$1]);
      expect(await storeA.pendingBookmarkOutbox(), hasLength(1));
    });
  });

  group('the row round-trips', () {
    test('every anchor field survives the store', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(
        _bookmark(
          media: BookmarkMedia.novel,
          index: 340,
          fraction: 0.5,
          total: 800,
          snippet: '…the mana core pulsed once.',
        ),
      );

      final stored = (await store.listBookmarks()).single;
      expect(stored.mediaType, BookmarkMedia.novel);
      expect(stored.anchorIndex, 340);
      expect(stored.anchorFraction, closeTo(0.5, 1e-9));
      expect(stored.anchorTotal, 800);
      expect(stored.snippet, '…the mana core pulsed once.');
      expect(stored.chapterNumber, 14);
      // The same arithmetic the server does, to the same 4 decimals.
      expect(stored.positionFraction, closeTo(0.4244, 1e-9));
    });

    test('listing is newest-changed first and hides tombstones', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(
        _bookmark(clientId: 'old', updatedAt: DateTime.utc(2026, 3, 4)),
      );
      await store.saveBookmark(
        _bookmark(clientId: 'new', updatedAt: DateTime.utc(2026, 6, 2)),
      );
      await store.saveBookmark(
        _bookmark(clientId: 'gone', updatedAt: DateTime.utc(2026, 7, 2)),
      );
      await store.tombstoneBookmark('gone');

      expect(
        (await store.listBookmarks()).map((b) => b.clientId),
        ['new', 'old'],
      );
    });
  });

  group('outbox', () {
    test('a create queues an upsert carrying the exact position', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());

      final queued = await store.pendingBookmarkOutbox().then((r) => r.single);
      expect(queued.$2.op, kBookmarkOpUpsert);
      expect(queued.$2.bookmark.clientId, 'c1');
      expect(queued.$2.bookmark.anchorIndex, 7);
      expect(queued.$2.bookmark.anchorFraction, closeTo(0.62, 1e-9));
      expect(queued.$2.bookmark.anchorTotal, 11);
      // The device's own clock rides along: it is what decides last-write-wins
      // between two devices, and a flush hours later must still be ordered by
      // when the reader actually acted.
      expect(queued.$2.toJson()['updated_at'], '2026-09-05T10:00:00.000Z');
    });

    test('create-then-delete flushes in that order, never reversed', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      await store.tombstoneBookmark('c1');

      final ops = await store.pendingBookmarkOutbox();
      expect(ops.map((o) => o.$2.op), [kBookmarkOpUpsert, kBookmarkOpDelete]);
    });

    test('clearing drains only the ids handed back', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      await store.saveBookmark(_bookmark(clientId: 'c2'));

      final ops = await store.pendingBookmarkOutbox();
      await store.clearBookmarkOutbox([ops.first.$1]);

      final left = await store.pendingBookmarkOutbox();
      expect(left.single.$2.bookmark.clientId, 'c2');
    });
  });

  group('a tombstone is terminal', () {
    test('re-saving a deleted client id is refused, not resurrected',
        () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      await store.tombstoneBookmark('c1');

      final again = await store.saveBookmark(_bookmark(index: 2));

      expect(again, isNull);
      expect((await store.getBookmark('c1'))!.deleted, isTrue);
      expect((await store.getBookmark('c1'))!.anchorIndex, 7);
      expect(await store.listBookmarks(), isEmpty);
    });

    test('deleting twice queues one delete', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      expect(await store.tombstoneBookmark('c1'), isTrue);
      expect(await store.tombstoneBookmark('c1'), isFalse);

      final ops = await store.pendingBookmarkOutbox();
      expect(ops.where((o) => o.$2.isDelete), hasLength(1));
    });

    test('deleting an id this scope never held changes nothing', () async {
      final store = harness.storeFor('u1p1');
      expect(await store.tombstoneBookmark('never-seen'), isFalse);
      expect(await store.pendingBookmarkOutbox(), isEmpty);
    });
  });

  group('mergeServerBookmarks', () {
    test('an unknown row is taken, tombstones included', () async {
      final store = harness.storeFor('u1p1');

      final written = await store.mergeServerBookmarks([
        _bookmark(clientId: 'live', id: 1),
        _bookmark(clientId: 'dead', id: 2, deleted: true),
      ]);

      expect(written, 2);
      expect((await store.listBookmarks()).map((b) => b.clientId), ['live']);
      // The tombstone is *learned*, not inferred from an absence — which is
      // how a delete made on the web reaches this phone at all.
      expect((await store.getBookmark('dead'))!.deleted, isTrue);
    });

    test('a local tombstone survives the server still listing it as live',
        () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      await store.tombstoneBookmark('c1');

      await store.mergeServerBookmarks([
        // Same client id as the row above — `_bookmark` defaults to it.
        _bookmark(id: 5, updatedAt: DateTime.utc(2027, 4, 5)),
      ]);

      expect((await store.getBookmark('c1'))!.deleted, isTrue);
      // The row id is still worth adopting.
      expect((await store.getBookmark('c1'))!.id, 5);
    });

    test('an unflushed local edit beats an older server row', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(
        _bookmark(index: 9, updatedAt: DateTime.utc(2026, 9, 5, 12)),
      );

      final written = await store.mergeServerBookmarks([
        _bookmark(index: 2, id: 4, updatedAt: DateTime.utc(2026, 9, 5, 10)),
      ]);

      expect(written, 0);
      expect((await store.getBookmark('c1'))!.anchorIndex, 9);
    });

    test('a newer server row wins', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(
        _bookmark(index: 9, updatedAt: DateTime.utc(2026, 9, 5, 10)),
      );

      await store.mergeServerBookmarks([
        _bookmark(index: 2, id: 4, updatedAt: DateTime.utc(2026, 9, 5, 12)),
      ]);

      expect((await store.getBookmark('c1'))!.anchorIndex, 2);
    });

    test('a server tombstone wins over a live local row', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());

      await store.mergeServerBookmarks([
        _bookmark(id: 4, deleted: true, updatedAt: DateTime.utc(2026, 9, 6)),
      ]);

      expect(await store.listBookmarks(), isEmpty);
    });

    test('rows absent from the listing are left alone', () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark(clientId: 'mine'));

      await store.mergeServerBookmarks([_bookmark(clientId: 'theirs', id: 8)]);

      // A listing is one page of one query; treating absence as deletion would
      // empty the screen the first time a response came back short.
      expect(
        (await store.listBookmarks()).map((b) => b.clientId),
        containsAll(['mine', 'theirs']),
      );
    });

    test('merging does not queue anything — a pull is not a change to push',
        () async {
      final store = harness.storeFor('u1p1');
      await store.mergeServerBookmarks([_bookmark(id: 1)]);
      expect(await store.pendingBookmarkOutbox(), isEmpty);
    });
  });

  group('adoptServerId', () {
    test('a bookmark made offline learns its server id on the first flush',
        () async {
      final store = harness.storeFor('u1p1');
      await store.saveBookmark(_bookmark());
      expect((await store.getBookmark('c1'))!.id, isNull);

      await store.adoptServerId('c1', 42);

      expect((await store.getBookmark('c1'))!.id, 42);
      // And only the id: the position it was saved with is untouched.
      expect((await store.getBookmark('c1'))!.anchorIndex, 7);
    });
  });

  group('schema v2 → v3 migration', () {
    /// The v2 schema, written by hand, so the upgrade is exercised against a
    /// database shaped exactly like the one already on the owner's phone
    /// rather than one this build created.
    Future<void> createV2Database(String path) async {
      final db = await openDatabase(
        path,
        version: 2,
        onCreate: (db, _) async {
          await db.execute('''
            CREATE TABLE saved_chapters (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              scope_id TEXT NOT NULL,
              source_id TEXT NOT NULL,
              series_key TEXT NOT NULL,
              chapter_key TEXT NOT NULL,
              chapter_number REAL,
              title TEXT,
              series_title TEXT,
              page_count INTEGER NOT NULL DEFAULT 0,
              bytes INTEGER NOT NULL DEFAULT 0,
              state TEXT NOT NULL,
              pinned INTEGER NOT NULL DEFAULT 0,
              read_at TEXT,
              created_at TEXT NOT NULL,
              retry_count INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              kind TEXT NOT NULL DEFAULT 'manga',
              UNIQUE(scope_id, source_id, series_key, chapter_key)
            )
          ''');
          await db.execute('''
            CREATE TABLE saved_pages (
              scope_id TEXT NOT NULL,
              chapter_rowid INTEGER NOT NULL,
              page_number INTEGER NOT NULL,
              blob_hash TEXT NOT NULL,
              size INTEGER NOT NULL,
              PRIMARY KEY (scope_id, chapter_rowid, page_number)
            )
          ''');
          await db.execute('''
            CREATE TABLE blobs (
              hash TEXT PRIMARY KEY,
              refcount INTEGER NOT NULL DEFAULT 0,
              size INTEGER NOT NULL
            )
          ''');
          await db.execute('''
            CREATE TABLE progress_outbox (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              scope_id TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
          ''');
        },
      );
      await db.insert('saved_chapters', {
        'scope_id': 'u1p1',
        'source_id': 'asurascans',
        'series_key': 'solo-leveling',
        'chapter_key': '132',
        'page_count': 3,
        'bytes': 900,
        'state': 'complete',
        'created_at': '2026-09-01T00:00:00.000Z',
        'kind': 'manga',
      });
      await db.insert('saved_pages', {
        'scope_id': 'u1p1',
        'chapter_rowid': 1,
        'page_number': 1,
        'blob_hash': 'abc',
        'size': 300,
      });
      await db.insert('blobs', {'hash': 'abc', 'refcount': 1, 'size': 300});
      await db.insert('progress_outbox', {
        'scope_id': 'u1p1',
        'payload_json': '{"source_id":"asurascans"}',
        'created_at': '2026-09-01T00:00:00.000Z',
      });
      await db.close();
    }

    test('a real v2 install keeps every row and gains the bookmark tables',
        () async {
      final path = '${harness.tempDir.path}/v2.db';
      await createV2Database(path);

      final upgraded = await openDownloadsDatabase(overridePath: path);
      addTearDown(upgraded.close);

      // Nothing the owner already had is touched. A destructive recreate
      // would take their downloads and their unflushed progress with it.
      expect(
        Sqflite.firstIntValue(
          await upgraded.rawQuery('SELECT COUNT(*) FROM saved_chapters'),
        ),
        1,
      );
      expect(
        Sqflite.firstIntValue(
          await upgraded.rawQuery('SELECT COUNT(*) FROM saved_pages'),
        ),
        1,
      );
      expect(
        Sqflite.firstIntValue(
          await upgraded.rawQuery('SELECT COUNT(*) FROM blobs'),
        ),
        1,
      );
      expect(
        Sqflite.firstIntValue(
          await upgraded.rawQuery('SELECT COUNT(*) FROM progress_outbox'),
        ),
        1,
      );
      expect(await upgraded.getVersion(), 3);

      // And the new tables are usable immediately, on the upgraded file.
      final store = DownloadsStore(
        scopeId: 'u1p1',
        database: Future.value(upgraded),
        blobStore: harness.openBlobStore(),
      );
      await store.saveBookmark(_bookmark());
      expect((await store.listBookmarks()).single.clientId, 'c1');
      expect(await store.pendingBookmarkOutbox(), hasLength(1));
    });

    test('an upgraded install and a fresh one have the same bookmark columns',
        () async {
      final upgradedPath = '${harness.tempDir.path}/upgraded.db';
      await createV2Database(upgradedPath);
      final upgraded = await openDownloadsDatabase(overridePath: upgradedPath);
      addTearDown(upgraded.close);

      final fresh = await openDownloadsDatabase(
        overridePath: '${harness.tempDir.path}/fresh.db',
      );
      addTearDown(fresh.close);

      Future<List<String>> columns(Database db, String table) async => [
            for (final row in await db.rawQuery('PRAGMA table_info($table)'))
              row['name']! as String,
          ];

      // One DDL function serves both paths precisely so these cannot drift.
      expect(
        await columns(upgraded, DownloadsSchema.bookmarks),
        await columns(fresh, DownloadsSchema.bookmarks),
      );
      expect(
        await columns(upgraded, DownloadsSchema.bookmarkOutbox),
        await columns(fresh, DownloadsSchema.bookmarkOutbox),
      );
    });
  });
}
