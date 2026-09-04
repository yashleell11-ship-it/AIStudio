import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:manhwamaniacs/features/downloads/models/download_chapter_state.dart';
import 'package:manhwamaniacs/features/downloads/models/saved_chapter.dart';
import 'package:manhwamaniacs/features/downloads/services/page_image_type.dart';
import 'package:manhwamaniacs/features/downloads/services/stored_zip.dart';
import 'package:manhwamaniacs/features/downloads/store/downloads_store.dart';
import 'package:manhwamaniacs/features/sources/utils/chapter_label.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

/// What an export writes out.
enum ChapterExportFormat {
  /// One folder per chapter holding numbered page images. The iOS Files app
  /// previews these inline and shows thumbnails, which is what actually
  /// answers "where did my download go" for someone holding a phone.
  images,

  /// One `.cbz` per chapter — a stored ZIP of the same numbered images, for
  /// moving a chapter somewhere else in a single file.
  cbz,
}

class ChapterExportResult {
  const ChapterExportResult({
    required this.directory,
    required this.seriesFolderName,
    required this.format,
    required this.chapterCount,
    required this.pageCount,
    required this.skippedCount,
  });

  /// The series folder everything landed in.
  final Directory directory;

  /// Its (sanitised) leaf name — what the user will actually see in Files.
  final String seriesFolderName;

  final ChapterExportFormat format;

  /// Chapters written.
  final int chapterCount;

  /// Page images written across those chapters.
  final int pageCount;

  /// Chapters passed in that had nothing exportable on disk — still
  /// downloading, failed, or missing a blob a user deleted by hand.
  final int skippedCount;

  bool get isEmpty => chapterCount == 0;
}

/// Writes a **readable copy** of already-downloaded chapters into
/// `Documents/Exports/<series>/`.
///
/// This exists because the store is content-addressed: page bytes live at
/// `Documents/mm-store/blobs/{hash[0:2]}/{sha256}`, which is correct (dedup
/// and refcounted deletion depend on it) and completely unusable to a human
/// browsing the Files app — thousands of extensionless files sharded across
/// 256 directories. Rather than compromise the store, this reprojects it on
/// demand into names a person can read.
///
/// **Strictly read-only with respect to the store.** It reads blob paths and
/// copies bytes; it never writes a `saved_pages` row, never touches a blob
/// refcount, and never deletes from the blob tree. The worst an export can
/// do is fill up `Documents/Exports`, which the user can delete from Files
/// with no effect on their downloads.
class ChapterExporter {
  ChapterExporter({required this.documentsDirectory});

  /// `getApplicationDocumentsDirectory()` in the app; a temp directory under
  /// test. Deliberately the *documents* directory and not application
  /// support: `UIFileSharingEnabled` + `LSSupportsOpeningDocumentsInPlace`
  /// (`ios/Runner/Info.plist`) surface only this one under
  /// *On My iPhone → ManhwaManiacs*.
  final Future<Directory> documentsDirectory;

  /// Top-level folder name inside Documents — a sibling of `mm-store`, so the
  /// readable copies sit next to (never inside) the content-addressed tree.
  static const String exportsFolderName = 'Exports';

  Future<ChapterExportResult> export({
    required DownloadsStore store,
    required String seriesLabel,
    required List<SavedChapter> chapters,
    required ChapterExportFormat format,
  }) async {
    final documents = await documentsDirectory;
    final folderName = sanitizeExportName(seriesLabel);
    final seriesDirectory =
        Directory(p.join(documents.path, exportsFolderName, folderName));
    await seriesDirectory.create(recursive: true);

    var exported = 0;
    var pages = 0;
    var skipped = 0;

    // Oldest chapter first, so a folder listing reads in reading order.
    final ordered = [...chapters]..sort(_byChapterOrder);

    for (final chapter in ordered) {
      if (chapter.state != DownloadChapterState.complete) {
        skipped++;
        continue;
      }
      final files = await store.localPagePaths(chapter.identity);
      // `localPagePaths` already drops pages whose blob has gone missing, so
      // a short map means the chapter is not wholly on disk — exporting a
      // partial chapter silently would be worse than reporting it skipped.
      if (files.length != chapter.pageCount || files.isEmpty) {
        skipped++;
        continue;
      }

      final stem = sanitizeExportName(
        chapterLabel(number: chapter.chapterNumber, title: chapter.title).primary,
      );
      pages += switch (format) {
        ChapterExportFormat.images =>
          await _writeImageFolder(seriesDirectory, stem, chapter, files),
        ChapterExportFormat.cbz =>
          await _writeCbz(seriesDirectory, stem, chapter, files),
      };
      exported++;
    }

    return ChapterExportResult(
      directory: seriesDirectory,
      seriesFolderName: folderName,
      format: format,
      chapterCount: exported,
      pageCount: pages,
      skippedCount: skipped,
    );
  }

  Future<int> _writeImageFolder(
    Directory seriesDirectory,
    String stem,
    SavedChapter chapter,
    Map<int, File> files,
  ) async {
    final chapterDirectory = Directory(p.join(seriesDirectory.path, stem));
    // Re-exporting after a re-download can change a page's format (sources
    // swap their CDN), which would otherwise leave a stale `004.jpg` beside
    // the new `004.webp` and break the page order.
    if (chapterDirectory.existsSync()) {
      await chapterDirectory.delete(recursive: true);
    }
    await chapterDirectory.create(recursive: true);

    final width = _pageNumberWidth(chapter.pageCount);
    var written = 0;
    for (var number = 1; number <= chapter.pageCount; number++) {
      final source = files[number];
      if (source == null) continue;
      final type = sniffPageImageType(await _readHeader(source));
      final name = '${number.toString().padLeft(width, '0')}${type.extension}';
      await source.copy(p.join(chapterDirectory.path, name));
      written++;
    }
    return written;
  }

  Future<int> _writeCbz(
    Directory seriesDirectory,
    String stem,
    SavedChapter chapter,
    Map<int, File> files,
  ) async {
    final target = File(p.join(seriesDirectory.path, '$stem.cbz'));
    final sink = target.openWrite();
    final zip = StoredZipWriter(sink.add);
    final width = _pageNumberWidth(chapter.pageCount);
    var written = 0;
    try {
      for (var number = 1; number <= chapter.pageCount; number++) {
        final source = files[number];
        if (source == null) continue;
        // One page in memory at a time — the writer streams straight through
        // to the sink rather than assembling the archive first.
        final bytes = await source.readAsBytes();
        final type = sniffPageImageType(bytes);
        zip.addFile(
          '${number.toString().padLeft(width, '0')}${type.extension}',
          bytes,
        );
        written++;
      }
      zip.finish();
    } finally {
      await sink.flush();
      await sink.close();
    }
    return written;
  }

  Future<List<int>> _readHeader(File file) async {
    final handle = await file.open();
    try {
      return await handle.read(kPageImageSniffLength);
    } finally {
      await handle.close();
    }
  }
}

/// Zero-pad page numbers so a lexical directory listing — which is all the
/// Files app and every extractor sort by — matches reading order. At least
/// three digits so short chapters still look deliberate.
int _pageNumberWidth(int pageCount) {
  final digits = pageCount.toString().length;
  return digits < 3 ? 3 : digits;
}

int _byChapterOrder(SavedChapter a, SavedChapter b) {
  final an = a.chapterNumber;
  final bn = b.chapterNumber;
  if (an != null && bn != null) return an.compareTo(bn);
  if (an != null) return -1;
  if (bn != null) return 1;
  return a.chapterKey.compareTo(b.chapterKey);
}

/// Turns a series or chapter title into something safe to use as a file name
/// on the device's filesystem *and* legible in the Files app.
///
/// Series titles come from connectors, so they can carry anything: slashes,
/// colons, percent-encoding, control characters, or (when a source gave no
/// title at all) a raw opaque `seriesKey` like `manga/solo-leveling`. Every
/// separator has to go — a slash here would silently write outside the
/// series folder.
String sanitizeExportName(String raw) {
  final cleaned = raw
      // Path separators and the characters Windows/macOS reject, plus C0
      // controls, all collapse to a space rather than vanish, so
      // "A/B" reads as "A B" instead of "AB".
      .replaceAll(RegExp(r'[\\/:*?"<>|\x00-\x1F]'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim()
      // A leading dot hides the entry on every Unix-derived filesystem, and
      // a name that is nothing but dots is a relative-path component; a
      // trailing dot or space is silently dropped by some filesystems.
      .replaceAll(RegExp(r'^[. ]+'), '')
      .replaceAll(RegExp(r'[. ]+$'), '')
      .trim();
  if (cleaned.isEmpty) return 'Untitled';
  // 255 bytes is the usual per-component limit; 80 characters keeps well
  // inside it even for multi-byte titles and stays readable in a file picker.
  return cleaned.length <= 80 ? cleaned : cleaned.substring(0, 80).trim();
}

/// Generous upper bound on resolving the documents directory — the same
/// "turn a wedged platform channel into a prompt failure rather than a hang"
/// guard `downloads_scope.dart` puts on the database and blob tree.
const _resolveTimeout = Duration(seconds: 3);

final chapterExporterProvider = Provider<ChapterExporter>(
  (ref) => ChapterExporter(
    documentsDirectory:
        getApplicationDocumentsDirectory().timeout(_resolveTimeout),
  ),
  name: 'chapterExporter',
);
