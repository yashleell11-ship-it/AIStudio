// Data-layer audit, shard "mobile-store". Each test here documents a claim
// the store's own doc comments make and checks whether the code keeps it.
// A FAILING test is the finding; a passing one is verification that the
// claim holds. Nothing in lib/ is modified by this file.
import 'dart:async';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/providers/currently_open_chapter_provider.dart';
import 'package:manhwamaniacs/features/downloads/providers/downloads_scope.dart';
import 'package:manhwamaniacs/features/downloads/services/blob_store.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_reader.dart';
import 'package:manhwamaniacs/features/downloads/services/retention_maintenance.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/downloads/widgets/open_chapter_scope.dart';
import 'package:manhwamaniacs/features/reader/models/reader_feed.dart';
import 'package:sqflite/sqflite.dart';

import '../support/downloads_test_support.dart';

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

/// A [BlobStore] whose `delete` lets a test interleave work between the
/// index transaction committing and the file actually being unlinked — the
/// exact window `deleteChapterAndBlobs` leaves open on purpose.
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

/// Records the read-stamp clears [OpenChapterScope] asks for without going
/// near the database: the question is *which* chapters it asks about, and
/// that is answerable synchronously.
class _RecordingStore extends DownloadsStore {
  _RecordingStore({
    required super.scopeId,
    required super.database,
    required super.blobStore,
  });

  final List<ChapterIdentity> cleared = [];

  @override
  Future<void> clearReadStamp(ChapterIdentity id) async => cleared.add(id);
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

  group('retention vs the continuous reader feed', () {
    test(
        'the resume sweep spares every chapter on screen in a Read-all feed, '
        'not just the ROUTE chapter', () async {
      final store = harness.storeFor('u1p1');
      final maintenance = RetentionMaintenance(
        database: harness.openDatabase(),
        blobStore: harness.openBlobStore(),
      );
      const route = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      const next = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c2');
      await _download(store, chapterKey: 'c1', seriesKey: 's');
      await _download(store, chapterKey: 'c2', seriesKey: 's');

      // c2 was finished three days ago (read_at stamped by an earlier read);
      // today the user re-enters the series at c1 in Read-all mode. Its stamp
      // is cleared as it enters the feed, so this fakes the worse case: the
      // sweep firing before that write lands.
      final db = await harness.openDatabase();
      await db.rawUpdate(
        "UPDATE saved_chapters SET read_at = ? WHERE chapter_key = 'c2'",
        [
          DateTime.now()
              .toUtc()
              .subtract(const Duration(days: 3))
              .toIso8601String(),
        ],
      );
      await store.clearReadStamp(route);

      // What the reader holds: the feed extended into c2 through the same
      // disk-first path the route came through (reader_screen._loadChapter).
      final feed = ReaderFeed.of([
        (await buildOfflineReaderChapter(store, route))!,
        (await buildOfflineReaderChapter(store, next))!,
      ]);
      expect(feed.chapters, hasLength(2));
      expect(feed.pages.every((p) => p.localFile!.existsSync()), isTrue);

      // The user backgrounds the app and comes back: DownloadsLifecycleGate
      // runs sweepExpired with excludeOpen = currentlyOpenChaptersProvider,
      // which the reader republishes from the feed on every window slide.
      final claimed = {
        for (final chapter in feed.chapters)
          (
            scopeId: 'u1p1',
            id: (sourceId: 'asura', seriesKey: 's', chapterKey: chapter.id),
          ),
      };
      await maintenance.sweepExpired(
        interval: const Duration(hours: 48),
        excludeOpen: claimed,
      );

      // Every page the feed is rendering must still be on disk.
      final gone = [
        for (final page in feed.pages)
          if (!page.localFile!.existsSync()) page.id,
      ];
      expect(
        gone,
        isEmpty,
        reason: 'the sweep unlinked pages that are in the on-screen feed',
      );
      expect(await store.isAvailableOffline(next), isTrue);
    });

    testWidgets(
        'the claim follows the window as it slides, and each chapter that '
        'ENTERS the feed has its expiry timer cancelled', (tester) async {
      const c1 = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      const c2 = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c2');
      const c3 = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c3');
      // Never completed: this double answers the only call the scope makes,
      // so opening a database here would only leave a handle for the
      // harness's teardown to delete out from under.
      final store = _RecordingStore(
        scopeId: 'u1p1',
        database: Completer<Database>().future,
        blobStore: Completer<BlobStore>().future,
      );
      final container = ProviderContainer(
        overrides: [
          activeDownloadsScopeIdProvider.overrideWithValue('u1p1'),
          downloadsStoreProvider.overrideWithValue(store),
        ],
      );
      addTearDown(container.dispose);

      Future<void> pumpWindow(List<ChapterIdentity> window) async {
        await tester.pumpWidget(
          UncontrolledProviderScope(
            container: container,
            child: OpenChapterScope(
              chapterId: c1, // the route never moves during a Read-all run
              feedChapterIds: window,
              child: const SizedBox.shrink(),
            ),
          ),
        );
        await tester.pump(); // the post-frame claim
      }

      await pumpWindow([c1, c2]);
      expect(container.read(currentlyOpenChaptersProvider), {
        (scopeId: 'u1p1', id: c1),
        (scopeId: 'u1p1', id: c2),
      });
      expect(store.cleared, [c1, c2]);

      // Two chapters in, the window has released c1 — the route's chapter is
      // no longer on screen, and c3 is.
      await pumpWindow([c2, c3]);
      expect(container.read(currentlyOpenChaptersProvider), {
        (scopeId: 'u1p1', id: c1),
        (scopeId: 'u1p1', id: c2),
        (scopeId: 'u1p1', id: c3),
      });
      // Only the newcomer: a window that slides back and forth over the same
      // chapter must not rewrite its row every frame.
      expect(store.cleared, [c1, c2, c3]);
    });
  });

  group('blob refcounting', () {
    test(
        're-saving a page number with DIFFERENT bytes writes an unreferenced '
        'blob file that nothing will ever reclaim', () async {
      final store = harness.storeFor('u1p1');
      final blobs = await harness.openBlobStore();
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowId = await store.ensureQueued(id: id);
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1, 1, 1]);
      // A retry racing a resume, or a source serving a re-encoded image the
      // second time: same page number, different bytes. The saved_pages
      // insert is IGNOREd — but BlobStore.write already ran.
      final secondHash = BlobStore.hashOf([2, 2, 2]);
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [2, 2, 2]);

      final db = await harness.openDatabase();
      final indexed = await db.query(
        DownloadsSchema.blobs,
        where: '${DownloadsSchema.colHash} = ?',
        whereArgs: [secondHash],
      );
      final onDisk = blobs.pathFor(secondHash).existsSync();

      // Either the file must not exist, or the index must know about it —
      // a file with no row is invisible to totalDeviceBytes() and to every
      // deletion path, i.e. a permanent leak.
      expect(
        onDisk && indexed.isEmpty,
        isFalse,
        reason: 'blob $secondHash is on disk with no blobs row',
      );
    });

    test(
        'the post-commit unlink deletes a blob another scope re-referenced '
        'between the index commit and the file delete (use-after-free)',
        () async {
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
      // this interleaving is the real one at every launch/resume.
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

  group('scope isolation', () {
    test(
        'rowId-keyed mutators (markFailed, updateManifestInfo, incrementRetry, '
        'markCompleteIfAllPagesPresent) do not check the row belongs to the '
        "store's own scope", () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u2p1');
      const idA = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowA = await storeA.ensureQueued(id: idA);

      // A store for a different user hands over A's rowId.
      await storeB.markFailed(rowId: rowA, error: 'poisoned from u2p1');

      final chapter = (await storeA.getChapter(idA))!;
      expect(
        chapter.state,
        DownloadChapterState.queued,
        reason: 'u2p1 changed the state of a u1p1 row',
      );
    });
  });

  group('schema migrations', () {
    /// The v1 schema (pre-novels, pre-bookmarks), by hand.
    Future<void> createV1Database(String path) async {
      final db = await openDatabase(
        path,
        version: 1,
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
          await db.execute(
            'CREATE INDEX idx_saved_pages_chapter ON saved_pages(scope_id, chapter_rowid)',
          );
          await db.execute(
            'CREATE INDEX idx_progress_outbox_scope ON progress_outbox(scope_id)',
          );
        },
      );
      await db.insert('saved_chapters', {
        'scope_id': 'u1p1',
        'source_id': 'asura',
        'series_key': 's',
        'chapter_key': '1',
        'page_count': 1,
        'bytes': 3,
        'state': 'complete',
        'created_at': '2026-08-01T00:00:00.000Z',
      });
      await db.close();
    }

    test('a v1 install upgraded straight to v3 matches a fresh create', () async {
      final upgradedPath = '${harness.tempDir.path}/v1.db';
      await createV1Database(upgradedPath);
      final upgraded = await openDownloadsDatabase(overridePath: upgradedPath);
      addTearDown(upgraded.close);
      final fresh = await openDownloadsDatabase(
        overridePath: '${harness.tempDir.path}/fresh.db',
      );
      addTearDown(fresh.close);

      expect(await upgraded.getVersion(), 3);

      Future<List<String>> columns(Database db, String table) async => [
            for (final row in await db.rawQuery('PRAGMA table_info($table)'))
              '${row['name']}:${row['type']}:nn=${row['notnull']}:'
                  'dflt=${row['dflt_value']}:pk=${row['pk']}',
          ];
      Future<List<String>> indexes(Database db, String table) async => [
            for (final row in await db.rawQuery('PRAGMA index_list($table)'))
              '${row['name']}:unique=${row['unique']}',
          ]..sort();

      for (final table in [
        DownloadsSchema.savedChapters,
        DownloadsSchema.savedPages,
        DownloadsSchema.blobs,
        DownloadsSchema.progressOutbox,
        DownloadsSchema.bookmarks,
        DownloadsSchema.bookmarkOutbox,
      ]) {
        expect(
          await columns(upgraded, table),
          await columns(fresh, table),
          reason: 'columns of $table drifted',
        );
        expect(
          await indexes(upgraded, table),
          await indexes(fresh, table),
          reason: 'indexes of $table drifted',
        );
      }
      // The pre-existing row survived and reads back as manga.
      final rows = await upgraded.query(DownloadsSchema.savedChapters);
      expect(rows.single[DownloadsSchema.colKind], kMangaDownloadKind);
    });
  });

  group('resume after a manifest change', () {
    test(
        'a chapter whose manifest shrank on re-fetch is marked complete but '
        'never reads as available offline (stale extra pages are not pruned)',
        () async {
      final store = harness.storeFor('u1p1');
      const id = (sourceId: 'asura', seriesKey: 's', chapterKey: 'c1');
      final rowId = await store.ensureQueued(id: id);
      // First pass: the manifest said 2 pages; both landed, app was killed
      // before markComplete.
      await store.updateManifestInfo(rowId: rowId, pageCount: 2);
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1]);
      await store.savePage(rowId: rowId, pageNumber: 2, bytes: [2]);
      // Resume: the source fixed the chapter, the manifest now says 1 page
      // (download_queue_controller.dart:601 re-runs updateManifestInfo on
      // every pass).
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);
      expect(
        (await store.getChapter(id))!.state,
        DownloadChapterState.complete,
      );
      // "complete" must mean readable offline.
      expect(
        await store.isAvailableOffline(id),
        isTrue,
        reason: 'localPagePaths has 2 entries, page_count is 1',
      );
      expect(await buildOfflineReaderChapter(store, id), isNotNull);
    });
  });

  group('downgrade then upgrade', () {
    test(
        'a v3 file opened once by an older (v1) build is unopenable by the '
        'current build afterwards: sqflite silently lowers user_version and '
        'the unguarded v1->v2 ALTER TABLE then fails on the existing column',
        () async {
      final path = '${harness.tempDir.path}/roundtrip.db';
      final current = await openDownloadsDatabase(overridePath: path);
      expect(await current.getVersion(), 3);
      await current.close();

      // An older sideloaded build: same tables it knows, version 1, and no
      // onDowngrade — exactly what downloads_db.dart passes to openDatabase.
      final older = await openDatabase(path, version: 1);
      expect(await older.getVersion(), 1, reason: 'sqflite lowered user_version');
      await older.close();

      // Back on the current build. The v1->v2 step runs ADD COLUMN kind on a
      // table that already has it.
      Database? reopened;
      try {
        reopened = await openDownloadsDatabase(overridePath: path);
      } finally {
        await reopened?.close();
      }
      expect(reopened, isNotNull);
    });
  });
}
