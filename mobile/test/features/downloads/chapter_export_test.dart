import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:manhwamaniacs/features/downloads/models/chapter_identity.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/services/chapter_export.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_db.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:path/path.dart' as p;

import '../../support/downloads_test_support.dart';
import '../../support/stored_zip_reader.dart';

/// Byte patterns whose *magic numbers* are real, since the exporter's whole
/// job is to name a file after what its bytes actually are. The blobs these
/// become carry no extension at all, exactly like the real store's.
List<int> _jpeg(int seed) => [0xFF, 0xD8, 0xFF, 0xE0, seed, seed, seed];
List<int> _png(int seed) =>
    [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, seed];
List<int> _webp(int seed) => [
      ...ascii.encode('RIFF'),
      0x10, 0, 0, 0,
      ...ascii.encode('WEBP'),
      seed,
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  initSqfliteFfiForTests();

  late TestDownloadsHarness harness;
  late DownloadsStore store;
  late Directory documents;
  late ChapterExporter exporter;

  setUp(() async {
    harness = await TestDownloadsHarness.create();
    store = harness.storeFor('u1p1');
    documents = Directory(p.join(harness.tempDir.path, 'documents'));
    await documents.create(recursive: true);
    exporter = ChapterExporter(documentsDirectory: Future.value(documents));
    // Force the FFI database open to finish inside setUp: the pure-function
    // tests below never touch the store, and would otherwise end while the
    // open was still in flight.
    await store.listChapters();
  });

  tearDown(() => harness.dispose());

  Future<SavedChapter> saveChapter({
    required String chapterKey,
    required double chapterNumber,
    required List<List<int>> pages,
    String seriesTitle = 'Solo Leveling',
    bool complete = true,
  }) async {
    final id = (
      sourceId: 'asura',
      seriesKey: 'solo-leveling',
      chapterKey: chapterKey,
    );
    final rowId = await store.ensureQueued(
      id: id,
      chapterNumber: chapterNumber,
      seriesTitle: seriesTitle,
    );
    await store.updateManifestInfo(rowId: rowId, pageCount: pages.length);
    for (var i = 0; i < pages.length; i++) {
      await store.savePage(rowId: rowId, pageNumber: i + 1, bytes: pages[i]);
    }
    if (complete) {
      expect(await store.markCompleteIfAllPagesPresent(rowId), isTrue);
    }
    return (await store.getChapter(id))!;
  }

  Directory exportsRoot() => Directory(
        p.join(documents.path, ChapterExporter.exportsFolderName),
      );

  group('page-image export', () {
    test('writes numbered pages named after their real format', () async {
      final chapter = await saveChapter(
        chapterKey: '12',
        chapterNumber: 12,
        pages: [_jpeg(1), _png(2), _webp(3)],
      );

      final result = await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );

      expect(result.chapterCount, 1);
      expect(result.pageCount, 3);
      expect(result.skippedCount, 0);
      expect(result.seriesFolderName, 'Solo Leveling');

      final dir = Directory(
        p.join(exportsRoot().path, 'Solo Leveling', 'Chapter 12'),
      );
      final names = dir.listSync().map((e) => p.basename(e.path)).toList()
        ..sort();
      // Zero-padded so a lexical listing — all the Files app sorts by — is
      // reading order, and extensions sniffed rather than assumed.
      expect(names, ['001.jpg', '002.png', '003.webp']);
      expect(File(p.join(dir.path, '002.png')).readAsBytesSync(), _png(2));
    });

    test('pads page numbers to the width of the chapter', () async {
      final chapter = await saveChapter(
        chapterKey: '1',
        chapterNumber: 1,
        pages: [for (var i = 0; i < 120; i++) _jpeg(i)],
      );

      await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );

      final dir =
          Directory(p.join(exportsRoot().path, 'Solo Leveling', 'Chapter 1'));
      final names = dir.listSync().map((e) => p.basename(e.path)).toList()
        ..sort();
      expect(names.first, '001.jpg');
      expect(names.last, '120.jpg');
    });

    test('re-exporting replaces the folder rather than layering on it',
        () async {
      final chapter = await saveChapter(
        chapterKey: '12',
        chapterNumber: 12,
        pages: [_jpeg(1), _png(2)],
      );
      await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );

      final dir =
          Directory(p.join(exportsRoot().path, 'Solo Leveling', 'Chapter 12'));
      // Stand in for a page whose source swapped format between downloads:
      // left behind, it would sort between the real pages and break the read.
      File(p.join(dir.path, '002.jpg')).writeAsBytesSync(_jpeg(9));

      await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );

      final names = dir.listSync().map((e) => p.basename(e.path)).toList()
        ..sort();
      expect(names, ['001.jpg', '002.png']);
    });
  });

  group('cbz export', () {
    test('produces a real ZIP holding the pages in order', () async {
      final chapter = await saveChapter(
        chapterKey: '12',
        chapterNumber: 12,
        pages: [_jpeg(1), _png(2), _webp(3)],
      );

      final result = await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.cbz,
      );

      expect(result.pageCount, 3);
      final file =
          File(p.join(exportsRoot().path, 'Solo Leveling', 'Chapter 12.cbz'));
      expect(file.existsSync(), isTrue);

      final entries = readStoredZip(
        Uint8List.fromList(file.readAsBytesSync()),
      );
      expect(entries.map((e) => e.name), ['001.jpg', '002.png', '003.webp']);
      expect(entries[2].bytes, _webp(3));
    });
  });

  group('what it refuses to export', () {
    test('skips chapters that are not fully on disk', () async {
      final done = await saveChapter(
        chapterKey: '1',
        chapterNumber: 1,
        pages: [_jpeg(1)],
      );
      final stillDownloading = await saveChapter(
        chapterKey: '2',
        chapterNumber: 2,
        pages: [_jpeg(2)],
        complete: false,
      );

      final result = await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [done, stillDownloading],
        format: ChapterExportFormat.images,
      );

      expect(result.chapterCount, 1);
      expect(result.skippedCount, 1);
      expect(
        Directory(p.join(exportsRoot().path, 'Solo Leveling', 'Chapter 2'))
            .existsSync(),
        isFalse,
      );
    });

    test('skips a chapter whose blob was deleted by hand', () async {
      final chapter = await saveChapter(
        chapterKey: '3',
        chapterNumber: 3,
        pages: [_jpeg(1), _png(2)],
      );
      // The Files app makes this possible: the index still lists two pages,
      // but one of them is gone. Half a chapter is not an export.
      final blobs = await harness.openBlobStore();
      final page = (await store.localPagePaths(chapter.identity))[1]!;
      expect(page.path.startsWith(blobs.rootDirectory.path), isTrue);
      page.deleteSync();

      final result = await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );

      expect(result.chapterCount, 0);
      expect(result.skippedCount, 1);
      expect(result.isEmpty, isTrue);
    });
  });

  test('leaves the store, its refcounts and its blobs untouched', () async {
    final chapter = await saveChapter(
      chapterKey: '12',
      chapterNumber: 12,
      pages: [_jpeg(1), _png(2), _jpeg(1)], // page 3 dedupes onto page 1
    );
    final db = await harness.openDatabase();
    Future<List<Map<String, Object?>>> snapshot(String table) =>
        db.query(table, orderBy: table == DownloadsSchema.blobs ? 'hash' : null);

    final blobsBefore = await snapshot(DownloadsSchema.blobs);
    final pagesBefore = await snapshot(DownloadsSchema.savedPages);
    final chaptersBefore = await snapshot(DownloadsSchema.savedChapters);
    // Two distinct blobs for three pages, the second one referenced twice —
    // precisely the bookkeeping an export must not disturb.
    expect(blobsBefore, hasLength(2));

    for (final format in ChapterExportFormat.values) {
      await exporter.export(
        store: store,
        seriesLabel: 'Solo Leveling',
        chapters: [chapter],
        format: format,
      );
    }

    expect(await snapshot(DownloadsSchema.blobs), blobsBefore);
    expect(await snapshot(DownloadsSchema.savedPages), pagesBefore);
    expect(await snapshot(DownloadsSchema.savedChapters), chaptersBefore);
    for (final file in (await store.localPagePaths(chapter.identity)).values) {
      expect(file.existsSync(), isTrue);
      expect(file.lengthSync(), greaterThan(0));
    }
  });

  group('sanitizeExportName', () {
    test('strips separators so an opaque series key cannot escape the folder',
        () {
      // seriesKey values are raw connector strings and routinely contain
      // slashes — 'manga/solo-leveling' must not become two directories, and
      // '..' must not climb out of Exports.
      expect(sanitizeExportName('manga/solo-leveling'), 'manga solo-leveling');
      expect(sanitizeExportName('../../etc'), 'etc');
      expect(sanitizeExportName(r'a\b:c*d?e"f<g>h|i'), 'a b c d e f g h i');
    });

    test('never returns a hidden, blank or trailing-dot name', () {
      expect(sanitizeExportName('   '), 'Untitled');
      expect(sanitizeExportName('...'), 'Untitled');
      expect(sanitizeExportName('.hidden'), 'hidden');
      expect(sanitizeExportName('Chapter 1.'), 'Chapter 1');
    });

    test('bounds the length for the filesystem', () {
      expect(sanitizeExportName('x' * 400).length, 80);
    });

    test('an untitled series still lands somewhere sensible', () async {
      final chapter = await saveChapter(
        chapterKey: 'c1',
        chapterNumber: 1,
        pages: [_jpeg(1)],
        seriesTitle: '',
      );
      final result = await exporter.export(
        store: store,
        // What the screen falls back to when a source gave no title.
        seriesLabel: 'manga/solo-leveling',
        chapters: [chapter],
        format: ChapterExportFormat.images,
      );
      expect(result.seriesFolderName, 'manga solo-leveling');
      expect(
        p.equals(result.directory.parent.path, exportsRoot().path),
        isTrue,
      );
    });
  });
}
