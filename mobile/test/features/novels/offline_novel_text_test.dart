import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/services/offline_novel_reader.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/novels/models/novel_chapter.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import '../../support/downloads_test_support.dart';

const _novel =
    (sourceId: 'royalroad', seriesKey: 'the-gate', chapterKey: 'c1');
const _manga =
    (sourceId: 'asura', seriesKey: 'solo-leveling', chapterKey: 'c1');

NovelChapter _chapterText({
  List<String> paragraphs = const [
    'The gate had stood shut for four hundred years.',
    '***',
    'Nobody living could remember who had closed it.',
  ],
}) =>
    NovelChapter(
      sourceId: _novel.sourceId,
      seriesKey: _novel.seriesKey,
      chapterKey: _novel.chapterKey,
      chapterNumber: 1,
      title: 'The Gate Opens',
      paragraphs: paragraphs,
      previousChapterKey: null,
      nextChapterKey: 'c2',
      wordCount: 17,
    );

Future<int> _downloadNovel(
  DownloadsStore store, {
  ChapterIdentity id = _novel,
  NovelChapter? text,
}) async {
  final rowId = await store.ensureQueued(id: id, kind: DownloadKind.novel);
  await store.updateManifestInfo(rowId: rowId, pageCount: 1);
  await store.saveNovelText(
    rowId: rowId,
    chapter: (text ?? _chapterText()).toStoredJson(),
  );
  await store.markCompleteIfAllPagesPresent(rowId);
  return rowId;
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

  group('a novel chapter is an ordinary row in the existing store', () {
    test('completes through the same guard a page-based chapter does',
        () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final saved = await store.getChapter(_novel);
      expect(saved, isNotNull);
      expect(saved!.state, DownloadChapterState.complete);
      expect(saved.kind, DownloadKind.novel);
      // One blob, not one page — but the completeness guard is the same one.
      expect(saved.pageCount, 1);
      expect(saved.bytes, greaterThan(0));
      expect(await store.isAvailableOffline(_novel), isTrue);
    });

    test('text blobs are tiny next to page images', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);
      final saved = await store.getChapter(_novel);
      // A whole chapter of prose, for less than a single page image's
      // thumbnail. This is why the storage cap needed no novel-shaped rule.
      expect(saved!.bytes, lessThan(4096));
    });

    test('per-series totals and the storage cap count it unchanged', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final breakdown = await store.seriesBreakdown();
      expect(breakdown, hasLength(1));
      expect(breakdown.first.sourceId, 'royalroad');
      expect(breakdown.first.chapterCount, 1);
      expect(breakdown.first.bytes, greaterThan(0));
      expect(await store.scopeBytes(), breakdown.first.bytes);
    });

    test('the read-then-expire sweep sees it like any other chapter', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      await store.markRead(_novel);
      expect((await store.getChapter(_novel))!.readAt, isNotNull);
      await store.clearReadStamp(_novel);
      expect((await store.getChapter(_novel))!.readAt, isNull);
    });

    test('removing it frees the blob through the same refcount path', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      await store.deleteDownload(_novel);
      expect(await store.getChapter(_novel), isNull);
      expect(await store.scopeBytes(), 0);
      expect(await store.readNovelText(_novel), isNull);
    });

    test('two profiles downloading the same chapter share one blob', () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');
      await _downloadNovel(storeA);
      await _downloadNovel(storeB);

      final db = await harness.openDatabase();
      final blobs = await db.query(DownloadsSchema.blobs);
      expect(blobs, hasLength(1));
      expect(blobs.first[DownloadsSchema.colRefcount], 2);

      // Deleting one profile's copy leaves the other's readable.
      await storeA.deleteDownload(_novel);
      expect(await storeB.readNovelText(_novel), isNotNull);
    });

    test("one profile's downloaded book is invisible to another", () async {
      final storeA = harness.storeFor('u1p1');
      final storeB = harness.storeFor('u1p2');
      await _downloadNovel(storeA);

      expect(await storeB.getChapter(_novel), isNull);
      expect(await buildOfflineNovelChapter(storeB, _novel), isNull);
    });
  });

  group('reading it back with no network', () {
    test('reconstructs the chapter end to end', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final chapter = await buildOfflineNovelChapter(store, _novel);
      expect(chapter, isNotNull);
      expect(chapter!.title, 'The Gate Opens');
      expect(chapter.chapterNumber, 1);
      expect(chapter.paragraphs, hasLength(3));
      expect(chapter.paragraphs.first, startsWith('The gate had stood'));
      expect(chapter.wordCount, 17);
      expect(chapter.isOffline, isTrue);
    });

    test('offers no prev/next, because the store does not know them', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final chapter = await buildOfflineNovelChapter(store, _novel);
      // The downloaded payload had a `next`; persisting it would let an
      // offline reader offer a link it cannot follow.
      expect(chapter!.previousChapterKey, isNull);
      expect(chapter.nextChapterKey, isNull);
    });

    test('a chapter still mid-download is not available offline', () async {
      final store = harness.storeFor('u1p1');
      final rowId =
          await store.ensureQueued(id: _novel, kind: DownloadKind.novel);
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);

      expect(await buildOfflineNovelChapter(store, _novel), isNull);
    });

    test('a manga chapter is never served as prose', () async {
      final store = harness.storeFor('u1p1');
      final rowId = await store.ensureQueued(id: _manga);
      await store.updateManifestInfo(rowId: rowId, pageCount: 1);
      await store.savePage(rowId: rowId, pageNumber: 1, bytes: [1, 2, 3]);
      await store.markCompleteIfAllPagesPresent(rowId);

      expect(await buildOfflineNovelChapter(store, _manga), isNull);
    });

    test('a blob deleted by hand degrades to "not available", never a crash',
        () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      // Exactly what the Files app lets a user do to the blob tree.
      final blobStore = await harness.openBlobStore();
      final db = await harness.openDatabase();
      final hash = (await db.query(DownloadsSchema.blobs))
          .first[DownloadsSchema.colHash]! as String;
      await blobStore.pathFor(hash).delete();

      expect(await store.readNovelText(_novel), isNull);
      expect(await buildOfflineNovelChapter(store, _novel), isNull);
    });

    test('a corrupt blob degrades the same way', () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final blobStore = await harness.openBlobStore();
      final db = await harness.openDatabase();
      final hash = (await db.query(DownloadsSchema.blobs))
          .first[DownloadsSchema.colHash]! as String;
      await blobStore.pathFor(hash).writeAsString('{not json');

      expect(await store.readNovelText(_novel), isNull);
      expect(await buildOfflineNovelChapter(store, _novel), isNull);
    });

    test('a blob that decoded but holds no prose is not a readable chapter',
        () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store, text: _chapterText(paragraphs: const []));

      expect(await store.readNovelText(_novel), isNotNull);
      expect(await buildOfflineNovelChapter(store, _novel), isNull);
    });

    test('the stored blob is the sanitized paragraphs and nothing else',
        () async {
      final store = harness.storeFor('u1p1');
      await _downloadNovel(store);

      final stored = await store.readNovelText(_novel);
      expect(
        stored!.keys,
        unorderedEquals(['title', 'chapter_number', 'paragraphs', 'word_count']),
      );
      // Network facts go stale; they are deliberately not persisted.
      expect(stored.containsKey('prev'), isFalse);
      expect(stored.containsKey('next'), isFalse);
    });
  });

  group('schema v2 migration', () {
    test('a pre-novels database upgrades in place, every row still manga',
        () async {
      // A v1 database, built the way the shipped app built one.
      final db = await databaseFactory.openDatabase(
        '${harness.tempDir.path}/legacy.db',
        options: OpenDatabaseOptions(
          version: 1,
          onCreate: (db, _) async {
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
                ${DownloadsSchema.colError} TEXT
              )
            ''');
            await db.insert(DownloadsSchema.savedChapters, {
              DownloadsSchema.colScopeId: 'u1p1',
              DownloadsSchema.colSourceId: 'asura',
              DownloadsSchema.colSeriesKey: 'solo-leveling',
              DownloadsSchema.colChapterKey: 'c1',
              DownloadsSchema.colPageCount: 12,
              DownloadsSchema.colBytes: 999,
              DownloadsSchema.colState: 'complete',
              DownloadsSchema.colCreatedAt:
                  DateTime.utc(2026).toIso8601String(),
            });
          },
        ),
      );
      await db.close();

      final upgraded =
          await openDownloadsDatabase(overridePath: '${harness.tempDir.path}/legacy.db');
      final rows = await upgraded.query(DownloadsSchema.savedChapters);
      expect(rows, hasLength(1));
      // The chapter that was already downloaded is untouched and manga.
      expect(rows.first[DownloadsSchema.colPageCount], 12);
      expect(rows.first[DownloadsSchema.colKind], kMangaDownloadKind);
      expect(
        SavedChapter.fromRow(rows.first).kind,
        DownloadKind.manga,
      );
      await upgraded.close();
    });
  });

  group('stored payload round-trip', () {
    test('survives JSON without losing a paragraph or a scene break', () {
      final original = _chapterText();
      final restored = NovelChapter.fromStoredJson(
        jsonDecode(jsonEncode(original.toStoredJson()))
            as Map<String, dynamic>,
        sourceId: _novel.sourceId,
        seriesKey: _novel.seriesKey,
        chapterKey: _novel.chapterKey,
      );
      expect(restored.paragraphs, original.paragraphs);
      expect(restored.title, original.title);
      expect(restored.chapterNumber, original.chapterNumber);
      expect(restored.wordCount, original.wordCount);
    });

    test('a payload with no word count recomputes one rather than showing 0',
        () {
      final restored = NovelChapter.fromStoredJson(
        {
          'title': 'X',
          'paragraphs': ['one two three'],
        },
        sourceId: 'a',
        seriesKey: 'b',
        chapterKey: 'c',
      );
      expect(restored.wordCount, 3);
    });
  });
}
