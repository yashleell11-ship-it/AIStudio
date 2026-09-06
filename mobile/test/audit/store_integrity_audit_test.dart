// Data-layer audit, shard "store-integrity": the on-device store's index and
// its blob tree must never disagree. Each group pins one finding (MS-2, MS-3,
// MS-4, MS-5, MS-6, MS-8) as the behaviour the store is now held to — a
// failing test here is a regression of that fix, not a new discovery.
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_reader.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_deletion.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:sqflite/sqflite.dart';

import '../support/downloads_test_support.dart';

String _hashOf(List<int> bytes) => sha256.convert(bytes).toString();

Future<int> _download(
  DownloadsStore store, {
  required String chapterKey,
  required String seriesKey,
  int pageCount = 2,
  int pageSize = 10,
}) async {
  final id = (sourceId: 'asura', seriesKey: seriesKey, chapterKey: chapterKey);
  final rowId = await store.ensureQueued(id: id);
  await store.updateManifestInfo(rowId: rowId, pageCount: pageCount);
  for (var page = 1; page <= pageCount; page++) {
    await store.savePage(
      rowId: rowId,
      pageNumber: page,
      bytes: List.filled(pageSize, (page + chapterKey.hashCode) & 0xff),
    );
  }
  expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);
  return rowId;
}

/// Makes a file look like it was written a while ago, so the orphan sweep's
/// "leave anything freshly written alone" margin does not shield it.
void _age(File file) => file.setLastModifiedSync(
      DateTime.now().subtract(const Duration(hours: 2)),
    );

/// A [BlobStore] whose `delete` lets a test start other work at the moment a
/// deletion path is about to unlink a file.
class _InterleavingBlobStore extends BlobStore {
  _InterleavingBlobStore({required super.rootDirectory});

  Future<void> Function(String hash)? beforeUnlink;

  @override
  Future<void> delete(String hash) async {
    final hook = beforeUnlink;
    beforeUnlink = null;
    if (hook != null) await hook(hash);
    await super.delete(hash);
  }
}

void main() {
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
  });

  tearDown(() async {
    await harness.dispose();
  });

  group('MS-2: savePage writes no blob the index will not reference', () {
    test('re-saving a page number with different bytes leaves no second file',
        () async {
      final store = harness.storeFor('u1p1');
      final blobs = await harness.openBlobStore();
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowId = await store.ensureQueued(id: id);
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1, 1, 1]);
      // A retry racing a resume, or a source serving a re-encoded image the
      // second time: same page number, different bytes. The row is a no-op
      // — so the file must be too.
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [2, 2, 2]);

      expect(
        blobs.pathFor(_hashOf([2, 2, 2])).existsSync(),
        isFalse,
        reason: 'the rejected bytes were written to disk anyway',
      );
      expect(blobs.pathFor(_hashOf([1, 1, 1])).existsSync(), isTrue);
      final db = await harness.openDatabase();
      expect(await db.query(DownloadsSchema.blobs), hasLength(1));
      expect((await store.getChapter(id))!.bytes, 3);
    });

    test(
        'a page arriving for a chapter row removed mid-download is rejected '
        'outright: no page row, no blob row, no file', () async {
      final store = harness.storeFor('u1p1');
      final blobs = await harness.openBlobStore();
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowId = await store.ensureQueued(id: id);
      await store.updateManifestInfo(rowId: rowId, pageCount: 2);
      // "Remove download" while the queue is still fetching pages.
      await store.deleteDownload(id);

      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [5, 5, 5]);

      final db = await harness.openDatabase();
      expect(await db.query(DownloadsSchema.savedPages), isEmpty);
      expect(await db.query(DownloadsSchema.blobs), isEmpty);
      expect(blobs.pathFor(_hashOf([5, 5, 5])).existsSync(), isFalse);
    });
  });

  group('MS-3: the post-commit unlink cannot race a re-reference', () {
    test(
        'a blob another scope re-references while a sweep is unlinking it is '
        'still on disk for that scope afterwards', () async {
      final racing = _InterleavingBlobStore(
        rootDirectory: Directory('${harness.tempDir.path}/blobs'),
      );
      final storeA = DownloadsStore(
        scopeId: 'u1p1',
        database: harness.openDatabase(),
        blobStore: Future.value(racing),
      );
      final storeB = DownloadsStore(
        scopeId: 'u1p2',
        database: harness.openDatabase(),
        blobStore: Future.value(racing),
      );
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: Future.value(racing),
      );
      const idA = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      const idB = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c9');
      final sharedPage = List<int>.filled(16, 7); // e.g. a credits page

      // Profile A finished c1 three days ago — it is due for the sweep.
      final rowA = await storeA.ensureQueued(id: idA);
      await storeA.updateManifestInfo(rowId: rowA, pageCount: 1);
      await storeA.savePage(rowId: rowA, pageNumber: 1, bytes: sharedPage);
      await storeA.markCompleteIfAllPagesPresent(rowA);
      final db = await harness.openDatabase();
      await db.rawUpdate(
        "UPDATE saved_chapters SET read_at = ? WHERE chapter_key = 'c1'",
        [
          DateTime.now()
              .toUtc()
              .subtract(const Duration(days: 3))
              .toIso8601String(),
        ],
      );

      // Profile B's queue is mid-download of c9, which shares that page.
      // DownloadsLifecycleGate._onActive fires _sweep() and
      // resumePendingOnLaunch() back to back without awaiting the sweep, so
      // B's save lands at whatever instant the sweep happens to be at — here,
      // the worst one: the sweep has decided the blob is unreferenced and is
      // about to unlink it. B's save is started but not awaited (the two
      // really are concurrent), and the sweep is held long enough that an
      // unguarded save would run to completion first.
      final rowB = await storeB.ensureQueued(id: idB);
      await storeB.updateManifestInfo(rowId: rowB, pageCount: 1);
      late Future<void> pendingSave;
      racing.beforeUnlink = (_) async {
        pendingSave =
            storeB.savePage(rowId: rowB, pageNumber: 1, bytes: sharedPage);
        await Future<void>.delayed(const Duration(milliseconds: 100));
      };

      await maintenance.sweepExpired(interval: const Duration(hours: 48));
      await pendingSave;
      expect(await storeB.markCompleteIfAllPagesPresent(rowB), isTrue);

      // B's index says the page is there (refcount 1) …
      final blobRows = await db.query(DownloadsSchema.blobs);
      expect(blobRows, hasLength(1));
      expect(blobRows.single[DownloadsSchema.colRefcount], 1);
      // … so the file must be too.
      expect(
        await storeB.isAvailableOffline(idB),
        isTrue,
        reason: "A's post-commit unlink removed the blob B had just re-referenced",
      );
    });
  });

  group('MS-4: a rolled-back APK never bricks the store', () {
    Future<List<String>> columns(Database db, String table) async => [
          for (final row in await db.rawQuery('PRAGMA table_info($table)'))
            '${row['name']}:${row['type']}:nn=${row['notnull']}:'
                'dflt=${row['dflt_value']}:pk=${row['pk']}',
        ];
    Future<List<String>> indexes(Database db, String table) async => [
          for (final row in await db.rawQuery('PRAGMA index_list($table)'))
            '${row['name']}:unique=${row['unique']}',
        ]..sort();

    Future<void> expectSchemaMatchesFresh(Database db) async {
      final fresh = await openDownloadsDatabase(
        overridePath: '${harness.tempDir.path}/fresh-${db.hashCode}.db',
      );
      addTearDown(fresh.close);
      for (final table in [
        DownloadsSchema.savedChapters,
        DownloadsSchema.savedPages,
        DownloadsSchema.blobs,
        DownloadsSchema.progressOutbox,
        DownloadsSchema.bookmarks,
        DownloadsSchema.bookmarkOutbox,
      ]) {
        expect(
          await columns(db, table),
          await columns(fresh, table),
          reason: 'columns of $table drifted',
        );
        expect(
          await indexes(db, table),
          await indexes(fresh, table),
          reason: 'indexes of $table drifted',
        );
      }
    }

    /// Writes one downloaded chapter through the real store into the file at
    /// [path] on the current build, then closes it.
    Future<void> seedCurrentBuild(String path) async {
      final current = await openDownloadsDatabase(overridePath: path);
      final store = DownloadsStore(
        scopeId: 'u1p1',
        database: Future.value(current),
        blobStore: harness.openBlobStore(),
      );
      await _download(store, chapterKey: 'c1', seriesKey: 's');
      expect(await current.getVersion(), 3);
      await current.close();
    }

    Future<void> expectIntactOnCurrentBuild(String path) async {
      final reopened = await openDownloadsDatabase(overridePath: path);
      addTearDown(reopened.close);
      expect(await reopened.getVersion(), 3);
      await expectSchemaMatchesFresh(reopened);
      final store = DownloadsStore(
        scopeId: 'u1p1',
        database: Future.value(reopened),
        blobStore: harness.openBlobStore(),
      );
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final chapter = await store.getChapter(id);
      expect(chapter, isNotNull, reason: 'the downloaded chapter was lost');
      expect(chapter!.state, DownloadChapterState.complete);
      expect(await store.isAvailableOffline(id), isTrue);
      final rows = await reopened.query(DownloadsSchema.savedChapters);
      expect(rows.single[DownloadsSchema.colKind], kMangaDownloadKind);
    }

    for (final olderVersion in [1, 2]) {
      test(
          'a v3 file opened once by a v$olderVersion build reopens on the '
          'current build with its downloads intact', () async {
        final path = '${harness.tempDir.path}/roundtrip-v$olderVersion.db';
        await seedCurrentBuild(path);

        // An older sideloaded build: no onDowngrade, so sqflite silently
        // lowers user_version — after which every upgrade step runs again.
        final older = await openDatabase(path, version: olderVersion);
        expect(await older.getVersion(), olderVersion);
        await older.close();

        await expectIntactOnCurrentBuild(path);
      });
    }

    test(
        'a file written by a NEWER build opens on this one (onDowngrade) with '
        'its downloads intact, and the round trip back up still works',
        () async {
      final path = '${harness.tempDir.path}/roundtrip-v4.db';
      await seedCurrentBuild(path);

      // A future build: additive, as every migration here has been.
      final newer = await openDatabase(
        path,
        version: 4,
        onUpgrade: (db, _, __) => db.execute(
          'CREATE TABLE IF NOT EXISTS future_table (x INTEGER)',
        ),
      );
      expect(await newer.getVersion(), 4);
      await newer.close();

      await expectIntactOnCurrentBuild(path);
    });
  });

  group('MS-5: a chapter completes against its CURRENT manifest', () {
    const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');

    test(
        'a chapter whose manifest shrank completes, reads offline, and has '
        'its stale page pruned from the index, the byte total and the disk',
        () async {
      final store = harness.storeFor('u1p1');
      final blobs = await harness.openBlobStore();
      final rowId = await store.ensureQueued(id: id);
      // First pass: the manifest said 2 pages; both landed, app was killed
      // before markComplete.
      await store.updateManifestInfo(rowId: rowId, pageCount: 2);
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1]);
      await store.savePage(rowId: rowId, pageNumber: 2, bytes: [2]);
      // Resume: the source fixed the chapter, the manifest now says 1 page.
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);
      final chapter = (await store.getChapter(id))!;
      expect(chapter.state, DownloadChapterState.complete);
      expect(
        await store.isAvailableOffline(id),
        isTrue,
        reason: '"complete" must mean readable offline',
      );
      expect(await buildOfflineReaderChapter(store, id), isNotNull);

      expect(await store.existingPageNumbers(rowId), {1});
      expect(chapter.bytes, 1, reason: 'the stale page still counts');
      final db = await harness.openDatabase();
      expect(await db.query(DownloadsSchema.blobs), hasLength(1));
      expect(
        blobs.pathFor(_hashOf([2])).existsSync(),
        isFalse,
        reason: 'the stale page\'s blob was left on disk',
      );
    });

    test('a stale page beyond the manifest never counts toward completeness',
        () async {
      final store = harness.storeFor('u1p1');
      final rowId = await store.ensureQueued(id: id);
      await store.updateManifestInfo(rowId: rowId, pageCount: 2);
      // Only page 2 landed before the kill …
      await store.savePage(rowId: rowId, pageNumber: 2, bytes: [2]);
      // … and on resume the manifest says 1 page — page 1, which is missing.
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      expect(await store.markCompleteIfAllPagesPresent(rowId), isFalse);
      expect(
        (await store.getChapter(id))!.state,
        DownloadChapterState.downloading,
      );
    });

    test('pruning a stale page keeps the blob another scope still references',
        () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');
      final blobs = await harness.openBlobStore();
      // B holds the bytes A is about to prune as its own single page.
      final rowB = await storeB.ensureQueued(id: id);
      await storeB.updateManifestInfo(rowId: rowB, pageCount: 1);
      await storeB.savePage(rowId: rowB, pageNumber: 1, bytes: [2]);
      expect(await storeB.markCompleteIfAllPagesPresent(rowB), isTrue);

      final rowA = await storeA.ensureQueued(id: id);
      await storeA.updateManifestInfo(rowId: rowA, pageCount: 2);
      await storeA.savePage(rowId: rowA, pageNumber: 1, bytes: [1]);
      await storeA.savePage(rowId: rowA, pageNumber: 2, bytes: [2]);
      await storeA.updateManifestInfo(rowId: rowA, pageCount: 1);
      expect(await storeA.markCompleteIfAllPagesPresent(rowA), isTrue);

      expect(blobs.pathFor(_hashOf([2])).existsSync(), isTrue);
      expect(await storeB.isAvailableOffline(id), isTrue);
      final db = await harness.openDatabase();
      final shared = await db.query(
        DownloadsSchema.blobs,
        where: '${DownloadsSchema.colHash} = ?',
        whereArgs: [_hashOf([2])],
      );
      expect(shared.single[DownloadsSchema.colRefcount], 1);
    });
  });

  group('MS-6: rowId-keyed writes are scope-checked', () {
    test("every rowId-keyed mutator is a no-op against another scope's row",
        () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u2p1');
      final blobs = await harness.openBlobStore();
      const idA = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowA = await storeA.ensureQueued(id: idA);

      // A store for a different user hands over A's rowId.
      await storeB.updateManifestInfo(rowId: rowA, pageCount: 9);
      await storeB.savePage(rowId: rowA, pageNumber: 1, bytes: [3, 3, 3]);
      expect(await storeB.markCompleteIfAllPagesPresent(rowA), isFalse);
      await storeB.incrementRetry(rowA);
      await storeB.markFailed(rowId: rowA, error: 'poisoned from u2p1');

      final chapter = (await storeA.getChapter(idA))!;
      expect(
        chapter.state,
        DownloadChapterState.queued,
        reason: 'u2p1 changed the state of a u1p1 row',
      );
      expect(chapter.pageCount, 0);
      expect(chapter.retryCount, 0);
      expect(chapter.error, isNull);
      expect(chapter.bytes, 0);
      final db = await harness.openDatabase();
      expect(await db.query(DownloadsSchema.savedPages), isEmpty);
      expect(await db.query(DownloadsSchema.blobs), isEmpty);
      expect(blobs.pathFor(_hashOf([3, 3, 3])).existsSync(), isFalse);
    });

    test("the shared deletion primitive cannot remove another scope's row",
        () async {
      final storeA = harness.storeFor('u1p1');
      const idA = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowA = await _download(storeA, chapterKey: 'c1', seriesKey: 's');

      await deleteChapterAndBlobs(
        db: await harness.openDatabase(),
        blobStore: await harness.openBlobStore(),
        chapterRowId: rowA,
        scopeId: 'u2p1',
      );

      expect(await storeA.getChapter(idA), isNotNull);
      expect(await storeA.isAvailableOffline(idA), isTrue);
    });
  });

  group('MS-8: the blob tree is garbage-collected from the sweep path', () {
    test(
        'a blob file with no index row is reclaimed by the resume sweep — '
        'even with read-then-expire switched Off — and referenced ones are not',
        () async {
      final store = harness.storeFor('u1p1');
      final blobs = await harness.openBlobStore();
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: harness.openBlobStore(),
      );
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      await _download(store, chapterKey: 'c1', seriesKey: 's');
      // A crash between a blob write and its index commit.
      final orphan = await blobs.write([9, 9, 9]);
      _age(blobs.pathFor(orphan.hash));
      for (final file in (await store.localPagePaths(id)).values) {
        _age(file);
      }

      expect(await maintenance.sweepExpired(interval: null), 0);

      expect(
        blobs.pathFor(orphan.hash).existsSync(),
        isFalse,
        reason: 'an unreferenced blob file is a permanent leak',
      );
      expect(await store.isAvailableOffline(id), isTrue);
    });

    test('an interrupted write (.part temp file) is swept', () async {
      final blobs = await harness.openBlobStore();
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: harness.openBlobStore(),
      );
      final hash = _hashOf([4, 4, 4]);
      final temp = File('${blobs.pathFor(hash).path}.part123456');
      await temp.parent.create(recursive: true);
      await temp.writeAsBytes([4, 4]); // truncated: the kill landed mid-write
      _age(temp);

      await maintenance.sweepExpired(interval: const Duration(hours: 48));

      expect(temp.existsSync(), isFalse);
    });

    test('a file written moments ago is left alone until a later run',
        () async {
      final blobs = await harness.openBlobStore();
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: harness.openBlobStore(),
      );
      final fresh = await blobs.write([8, 8, 8]);

      await maintenance.sweepExpired(interval: const Duration(hours: 48));

      expect(blobs.pathFor(fresh.hash).existsSync(), isTrue);
    });

    test('one run reclaims at most its budget, and the next run resumes',
        () async {
      final blobs = await harness.openBlobStore();
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: harness.openBlobStore(),
      );
      // The sweep runs on the launch/resume path, beside the work the user is
      // waiting for. A tree that accumulated a lot of garbage must not turn
      // one launch into a long stall — the leftovers keep until next time.
      for (var i = 0; i < 3; i++) {
        _age(blobs.pathFor((await blobs.write([i, i, i])).hash));
      }

      expect(
        await maintenance.reclaimOrphanBlobs(grace: Duration.zero, perRun: 2),
        2,
      );
      expect(await blobs.hashesOnDisk(), hasLength(1));

      expect(
        await maintenance.reclaimOrphanBlobs(grace: Duration.zero, perRun: 2),
        1,
      );
      expect(await blobs.hashesOnDisk(), isEmpty);
    });
  });
}
